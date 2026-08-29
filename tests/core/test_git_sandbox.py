"""Tests for Git sandbox lifecycle."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import worktree.core.git_sandbox as git_sandbox_mod
from tests.helpers import FileSystem, GitFileSystem
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.git_sandbox import (
    GitSandboxManager,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateStatus,
    SandboxDiffStatus,
    SandboxSession,
)


def _init_git_repo(path: Path, branch: str = "feature") -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


class GitSandboxManagerTests:
    """Integration tests against a real git repository."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path)

    def test_create_and_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_test1")
        assert result.ok
        assert result.status == SandboxCreateStatus.OK
        assert result.session is not None
        session = result.session
        assert session.sandbox_path.is_dir()
        assert session.sandbox_path.is_absolute()
        assert session.target_branch == "worktree/sandbox-sbx_test1"
        assert (session.sandbox_path / "f.txt").is_file()
        manager.cleanup_sandbox(session)
        assert not session.sandbox_path.exists()

    def test_create_sandbox_wrapper_raises(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_wrap")
        assert session.session_id == "sbx_wrap"
        manager.cleanup_sandbox(session)

    def test_default_session_id_pattern(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox()
        assert re.fullmatch(r"sbx_[0-9a-f]{8}", session.session_id)
        assert session.target_branch == f"worktree/sandbox-{session.session_id}"
        manager.cleanup_sandbox(session)

    def test_get_active_sandboxes_dirs_only(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        assert manager.get_active_sandboxes() == []
        manager.sandbox_base_dir.mkdir(parents=True, exist_ok=True)
        (manager.sandbox_base_dir / "note.txt").write_text("x\n", encoding="utf-8")
        assert manager.get_active_sandboxes() == []
        session = manager.create_sandbox(session_id="sbx_active")
        active = manager.get_active_sandboxes()
        assert session.sandbox_path in active
        manager.cleanup_sandbox(session)

    def test_max_active_enforced_result(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["max_active_sandboxes"] = 1
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        manager = GitSandboxManager(path=git_fs.base_path)
        first = manager.create_sandbox(session_id="sbx_a")
        second = manager.create_sandbox_result(session_id="sbx_b")
        assert not second.ok
        assert second.status == SandboxCreateStatus.CAPACITY_EXCEEDED
        assert second.session is None
        assert "Maximum active sandboxes reached (1/1)." in second.errors[0]
        assert "wt prune" in second.errors[0]
        assert not (manager.sandbox_base_dir / "sbx_b").exists()
        with pytest.raises(RuntimeError, match="Maximum active sandboxes reached"):
            manager.create_sandbox(session_id="sbx_b")
        manager.cleanup_sandbox(first)

    def test_not_initialized(self, fs: FileSystem) -> None:
        _init_git_repo(fs.base_path)
        manager = GitSandboxManager(path=fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_x")
        assert result.status == SandboxCreateStatus.NOT_INITIALIZED
        assert "SANDBOX_NOT_INITIALIZED" in result.errors[0]
        assert "wt init" in result.errors[0]

    def test_unreadable_config(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text("{ not-json\n", encoding="utf-8")
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_badcfg")
        assert result.status == SandboxCreateStatus.UNREADABLE_CONFIG
        assert "SANDBOX_CONFIG_UNREADABLE" in result.errors[0]

    def test_git_failed_invalid_base_ref(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["base_ref"] = "refs/does-not-exist"
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        # Detach HEAD so create falls back to config base_ref.
        subprocess.run(
            ["git", "checkout", "--detach", "HEAD"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_badref")
        assert result.status == SandboxCreateStatus.GIT_FAILED
        assert result.session is None
        assert "SANDBOX_GIT_FAILED" in result.errors[0]
        assert not (manager.sandbox_base_dir / "sbx_badref").exists()

    def test_git_timeout_on_worktree_add(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)

        def _timeout(*_args: object, **_kwargs: object) -> object:
            raise subprocess.TimeoutExpired(cmd=["git", "worktree", "add"], timeout=120)

        monkeypatch.setattr(git_sandbox_mod.subprocess, "run", _timeout)
        result = manager.create_sandbox_result(session_id="sbx_to")
        assert result.status == SandboxCreateStatus.GIT_TIMEOUT
        assert result.session is None
        assert "SANDBOX_GIT_TIMEOUT" in result.errors[0]
        assert "GIT_TIMEOUT" in result.errors[0]
        assert not (manager.sandbox_base_dir / "sbx_to").exists()

    def test_cleanup_idempotent(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_idemp")
        manager.cleanup_sandbox(session)
        manager.cleanup_sandbox(session)  # must not raise

    def test_config_property_none_until_create_loads(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        assert manager.config is None
        session = manager.create_sandbox(session_id="sbx_cfg")
        assert manager.config is not None
        manager.cleanup_sandbox(session)

    def test_cleanup_missing_path_and_branch(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        ghost = SandboxSession(
            session_id="sbx_ghost",
            target_branch="worktree/sandbox-sbx_ghost",
            sandbox_path=manager.sandbox_base_dir / "sbx_ghost",
            base_commit="0" * 40,
            created_at="2020-01-01T00:00:00+00:00",
        )
        manager.cleanup_sandbox(ghost)  # must not raise

    def test_base_ref_uses_current_branch(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_br")
        head = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=session.sandbox_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert head == session.target_branch
        # Branch created from feature tip
        tip_main = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tip_sbx = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=session.sandbox_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert tip_main == tip_sbx
        manager.cleanup_sandbox(session)

    def test_include_wip_copies_uncommitted_changes(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        (git_fs.base_path / "f.txt").write_text("dirty\n", encoding="utf-8")
        (git_fs.base_path / "new.txt").write_text("untracked\n", encoding="utf-8")

        manager = GitSandboxManager(path=git_fs.base_path)
        clean = manager.create_sandbox_result(session_id="sbx_nowip")
        assert clean.ok and clean.session is not None
        assert clean.session.wip_applied is False
        assert (clean.session.sandbox_path / "f.txt").read_text(encoding="utf-8") == ("x\n")
        assert not (clean.session.sandbox_path / "new.txt").exists()
        manager.cleanup_sandbox(clean.session)

        wip = manager.create_sandbox_result(session_id="sbx_wip", include_wip=True)
        assert wip.ok and wip.session is not None
        assert wip.session.wip_applied is True
        assert "f.txt" in wip.session.wip_paths
        assert "new.txt" in wip.session.wip_paths
        assert (wip.session.sandbox_path / "f.txt").read_text(encoding="utf-8") == ("dirty\n")
        assert (wip.session.sandbox_path / "new.txt").read_text(encoding="utf-8") == "untracked\n"
        manager.cleanup_sandbox(wip.session)

    def test_include_wip_deletes_removed_tracked_file(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        (git_fs.base_path / "f.txt").unlink()
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_del", include_wip=True)
        assert result.ok and result.session is not None
        assert "f.txt" in result.session.wip_paths
        assert not (result.session.sandbox_path / "f.txt").exists()
        manager.cleanup_sandbox(result.session)

    def test_base_commit_resolved_on_create(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        expected = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_base")
        assert result.ok and result.session is not None
        assert result.session.base_commit == expected
        manager.cleanup_sandbox(result.session)

    def test_name_threading_and_whitespace_normalization(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        named = manager.create_sandbox_result(session_id="sbx_name", name="  demo  ")
        assert named.ok and named.session is not None
        assert named.session.name == "demo"
        manager.cleanup_sandbox(named.session)

        blank = manager.create_sandbox_result(session_id="sbx_blank", name="   ")
        assert blank.ok and blank.session is not None
        assert blank.session.name is None
        manager.cleanup_sandbox(blank.session)

        none_name = manager.create_sandbox_result(session_id="sbx_noname")
        assert none_name.ok and none_name.session is not None
        assert none_name.session.name is None
        manager.cleanup_sandbox(none_name.session)

    def test_base_ref_override(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        (git_fs.base_path / "other.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "other.txt"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "other tip"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        other_tip = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        feature_tip = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert other_tip != feature_tip

        manager = GitSandboxManager(path=git_fs.base_path)
        # On branch other; override back to feature tip.
        overridden = manager.create_sandbox_result(
            session_id="sbx_override",
            base_ref="feature",
        )
        assert overridden.ok and overridden.session is not None
        assert overridden.session.base_commit == feature_tip
        manager.cleanup_sandbox(overridden.session)

        blank = manager.create_sandbox_result(
            session_id="sbx_blankref",
            base_ref="   ",
        )
        assert blank.ok and blank.session is not None
        assert blank.session.base_commit == other_tip
        manager.cleanup_sandbox(blank.session)

        bad = manager.create_sandbox_result(
            session_id="sbx_badoverride",
            base_ref="refs/does-not-exist",
        )
        assert bad.status == SandboxCreateStatus.GIT_FAILED
        assert not bad.ok

    def test_persists_active_row_on_create(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_db1", name="persist-me")
        assert result.ok and result.session is not None
        assert result.warnings == []
        row = self.db.sandboxes.get("sbx_db1")
        assert row is not None
        assert row.status == SandboxStatus.ACTIVE
        assert row.name == "persist-me"
        assert row.branch_name == result.session.target_branch
        assert row.base_commit == result.session.base_commit
        assert row.sandbox_path == result.session.sandbox_path
        manager.cleanup_sandbox(result.session)

    def test_marks_cleaned_on_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_db2")
        assert self.db.sandboxes.get("sbx_db2") is not None
        manager.cleanup_sandbox(session)
        row = self.db.sandboxes.get("sbx_db2")
        assert row is not None
        assert row.status == SandboxStatus.CLEANED

    def test_create_failure_surfaces_as_warning(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db locked")

        monkeypatch.setattr("worktree.core.db.repositories.sandboxes.SandboxesRepository.create", _boom)
        manager = GitSandboxManager(path=git_fs.base_path)
        result = manager.create_sandbox_result(session_id="sbx_warn")
        assert result.ok and result.session is not None
        assert result.session.sandbox_path.is_dir()
        assert len(result.warnings) == 1
        assert "db locked" in result.warnings[0]
        assert self.db.sandboxes.get("sbx_warn") is None
        manager.cleanup_sandbox(result.session)

    def test_cleanup_without_db_row_does_not_raise(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        ghost = SandboxSession(
            session_id="sbx_norow",
            target_branch="worktree/sandbox-sbx_norow",
            sandbox_path=manager.sandbox_base_dir / "sbx_norow",
            base_commit="0" * 40,
            created_at="2020-01-01T00:00:00+00:00",
        )
        manager.cleanup_sandbox(ghost)  # must not raise

    def test_rev_parse_failure_is_git_failed(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        real_run = subprocess.run

        def _run(cmd: list[str], *args: object, **kwargs: object) -> object:
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1:3] == ["rev-parse", "HEAD"]:
                raise subprocess.CalledProcessError(1, cmd, stderr="rev-parse exploded")
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(git_sandbox_mod.subprocess, "run", _run)
        result = manager.create_sandbox_result(session_id="sbx_rp")
        assert result.status == SandboxCreateStatus.GIT_FAILED
        assert result.session is None
        assert "SANDBOX_GIT_FAILED" in result.errors[0]
        assert not (manager.sandbox_base_dir / "sbx_rp").exists()

    def test_apply_sandbox_patch_strategy_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_app1")

        # Make modifications in the sandbox
        (session.sandbox_path / "new_file.py").write_text("print('hello')\n", encoding="utf-8")
        (session.sandbox_path / "f.txt").write_text("modified in sandbox\n", encoding="utf-8")

        result = manager.apply_sandbox_result(session.session_id, strategy=SandboxApplyStrategy.PATCH)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert result.strategy == SandboxApplyStrategy.PATCH
        assert set(result.touched_files) == {"new_file.py", "f.txt"}
        assert (git_fs.base_path / "new_file.py").read_text(encoding="utf-8") == "print('hello')\n"
        assert (git_fs.base_path / "f.txt").read_text(encoding="utf-8") == "modified in sandbox\n"

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.MERGED
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_squash_strategy_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_sq")

        (session.sandbox_path / "feature.py").write_text("def feat(): pass\n", encoding="utf-8")

        result = manager.apply_sandbox_result(
            session.session_id,
            strategy=SandboxApplyStrategy.SQUASH,
            message="feat: add feature",
        )
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert result.strategy == SandboxApplyStrategy.SQUASH
        assert result.commit_sha is not None
        assert len(result.commit_sha) == 40
        assert (git_fs.base_path / "feature.py").exists()

        log_proc = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"], cwd=git_fs.base_path, capture_output=True, text=True, check=True
        )
        assert "feat: add feature" in log_proc.stdout
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_with_delete_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_del")

        (session.sandbox_path / "del_test.txt").write_text("abc\n", encoding="utf-8")

        result = manager.apply_sandbox_result(session.session_id, delete=True)
        assert result.ok
        assert result.cleaned_up
        assert not session.sandbox_path.exists()

        branch_proc = subprocess.run(
            ["git", "branch", "--list", session.target_branch],
            cwd=git_fs.base_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert session.target_branch not in branch_proc.stdout

    def test_apply_sandbox_main_repo_dirty_aborts(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_dirty")

        (session.sandbox_path / "a.txt").write_text("a\n", encoding="utf-8")

        # Make main workspace dirty
        (git_fs.base_path / "f.txt").write_text("dirty in main\n", encoding="utf-8")

        result = manager.apply_sandbox_result(session.session_id, allow_dirty=False)
        assert not result.ok
        assert result.status == SandboxApplyStatus.MAIN_REPO_DIRTY
        assert "uncommitted changes" in result.errors[0]

        # Reset main repo for cleanup
        subprocess.run(["git", "checkout", "--", "f.txt"], cwd=git_fs.base_path, check=True, capture_output=True)
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_main_repo_dirty_allowed(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_allow_dirty")

        (session.sandbox_path / "other.txt").write_text("other\n", encoding="utf-8")

        # Make main workspace dirty in unrelated file
        (git_fs.base_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        result = manager.apply_sandbox_result(session.session_id, allow_dirty=True)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert (git_fs.base_path / "other.txt").exists()
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_empty_diff(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_empty")

        # No changes made in sandbox
        result = manager.apply_sandbox_result(session.session_id)
        assert result.status == SandboxApplyStatus.EMPTY_DIFF
        assert not result.touched_files
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_conflict_detected(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_conf")

        # Sandbox edits line 1 of f.txt
        (session.sandbox_path / "f.txt").write_text("sandbox line\n", encoding="utf-8")

        # Main workspace commits a conflicting edit to f.txt
        (git_fs.base_path / "f.txt").write_text("main line\n", encoding="utf-8")
        subprocess.run(
            ["git", "commit", "-am", "conflicting commit"], cwd=git_fs.base_path, check=True, capture_output=True
        )

        result = manager.apply_sandbox_result(session.session_id, allow_dirty=False)
        assert not result.ok
        assert result.status == SandboxApplyStatus.CONFLICT
        assert "f.txt" in result.conflicting_files

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.CONFLICT
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_dry_run(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_dry")

        (session.sandbox_path / "dry.txt").write_text("dry test\n", encoding="utf-8")

        result = manager.apply_sandbox_result(session.session_id, dry_run=True)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert not (git_fs.base_path / "dry.txt").exists()

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.ACTIVE
        manager.cleanup_sandbox(session)

    def test_apply_sandbox_not_found_and_missing_disk(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)

        res_missing = manager.apply_sandbox_result("sbx_nonexistent")
        assert res_missing.status == SandboxApplyStatus.NOT_FOUND

        session = manager.create_sandbox(session_id="sbx_disk_gone")
        # Remove directory manually
        import shutil

        shutil.rmtree(session.sandbox_path)

        res_disk = manager.apply_sandbox_result(session.session_id)
        assert res_disk.status == SandboxApplyStatus.NOT_FOUND

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.CLEANED

    def test_apply_sandbox_already_merged(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_already")

        (session.sandbox_path / "f.txt").write_text("merged\n", encoding="utf-8")
        manager.apply_sandbox(session.session_id)

        # Apply again
        res2 = manager.apply_sandbox_result(session.session_id)
        assert res2.status == SandboxApplyStatus.ALREADY_MERGED
        manager.cleanup_sandbox(session)

    def test_diff_sandbox(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path)
        session = manager.create_sandbox(session_id="sbx_diff")

        (session.sandbox_path / "diff_test.txt").write_text("hello diff\n", encoding="utf-8")

        diff_res = manager.diff_sandbox_result(session.session_id)
        assert diff_res.ok
        assert diff_res.status == SandboxDiffStatus.OK
        assert "diff --git a/diff_test.txt b/diff_test.txt" in diff_res.diff_text
        assert "diff_test.txt" in diff_res.files_changed

        stat_res = manager.diff_sandbox_result(session.session_id, stat=True)
        assert stat_res.ok
        assert "diff_test.txt | 1 +" in stat_res.stat_text

        manager.cleanup_sandbox(session)
