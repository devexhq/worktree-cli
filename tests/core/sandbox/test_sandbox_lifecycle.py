"""Tests for SandboxLifecycle service and WIP overlay operations."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers import FileSystem, GitFileSystem
from worktree.core.config import ConfigLoadError
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.git.exceptions import GitPlumbingTimeoutError
from worktree.core.sandbox import (
    SandboxCreateStatus,
    SandboxSession,
)
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.wip import apply_wip_to_sandbox, copy_wip_file, list_wip_paths


def _init_git_repo(path: Path, branch: str = "feature") -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class TestSandboxLifecycle:
    """Tests for SandboxLifecycle domain service."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path)

    def test_create_and_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        result = lifecycle.create(session_id="sbx_test1")
        assert result.ok
        assert result.status == SandboxCreateStatus.OK
        assert result.session is not None
        session = result.session
        assert session.sandbox_path.is_dir()
        assert session.sandbox_path.is_absolute()
        assert session.target_branch == "worktree/sandbox-sbx_test1"
        assert (session.sandbox_path / "f.txt").is_file()
        lifecycle.cleanup(session)
        assert not session.sandbox_path.exists()

    def test_default_session_id_pattern(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        result = lifecycle.create()
        assert result.ok and result.session is not None
        assert re.fullmatch(r"sbx_[0-9a-f]{8}", result.session.session_id)
        assert result.session.target_branch == f"worktree/sandbox-{result.session.session_id}"
        lifecycle.cleanup(result.session)

    def test_get_active_sandboxes_dirs_only(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        assert lifecycle.get_active() == []
        lifecycle.sandbox_base_dir.mkdir(parents=True, exist_ok=True)
        (lifecycle.sandbox_base_dir / "note.txt").write_text("x\n", encoding="utf-8")
        assert lifecycle.get_active() == []
        res = lifecycle.create(session_id="sbx_active")
        assert res.ok and res.session is not None
        active = lifecycle.get_active()
        assert res.session.sandbox_path in active
        lifecycle.cleanup(res.session)

    def test_max_active_enforced(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["max_active_sandboxes"] = 1
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        first = lifecycle.create(session_id="sbx_a")
        assert first.ok and first.session is not None
        second = lifecycle.create(session_id="sbx_b")
        assert not second.ok
        assert second.status == SandboxCreateStatus.CAPACITY_EXCEEDED
        assert second.session is None
        assert "Maximum active sandboxes reached (1/1)." in second.errors[0]
        assert "wt prune" in second.errors[0]
        assert not (lifecycle.sandbox_base_dir / "sbx_b").exists()
        lifecycle.cleanup(first.session)

    def test_create_raises_when_uninitialized(self, fs: FileSystem) -> None:
        _init_git_repo(fs.base_path)
        db = WorktreeDb(path=fs.base_path)
        lifecycle = SandboxLifecycle(path=fs.base_path, db=db.sandboxes)
        with pytest.raises(ConfigLoadError):
            lifecycle.create(session_id="sbx_x")

    def test_create_raises_on_unreadable_config(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text("{ not-json\n", encoding="utf-8")
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        with pytest.raises(ConfigLoadError):
            lifecycle.create(session_id="sbx_badcfg")

    def test_git_failed_invalid_base_ref(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["base_ref"] = "refs/does-not-exist"
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=git_fs.base_path, check=True, capture_output=True)
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        result = lifecycle.create(session_id="sbx_badref")
        assert result.status == SandboxCreateStatus.GIT_FAILED
        assert result.session is None
        assert "SANDBOX_GIT_FAILED" in result.errors[0]
        assert not (lifecycle.sandbox_base_dir / "sbx_badref").exists()

    def test_git_timeout_on_worktree_add(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)

        with patch("worktree.core.git.runner.GitRunner.worktree_add", side_effect=GitPlumbingTimeoutError("timeout")):
            result = lifecycle.create(session_id="sbx_to")
            assert result.status == SandboxCreateStatus.GIT_TIMEOUT
            assert result.session is None
            assert "SANDBOX_GIT_TIMEOUT" in result.errors[0]
            assert not (lifecycle.sandbox_base_dir / "sbx_to").exists()

    def test_cleanup_idempotent(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_idemp")
        assert res.ok and res.session is not None
        lifecycle.cleanup(res.session)
        lifecycle.cleanup(res.session)  # must not raise

    def test_config_property(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        assert lifecycle.config is not None
        assert lifecycle.config.project.name == "repo"
        res = lifecycle.create(session_id="sbx_cfg")
        assert res.ok and res.session is not None
        lifecycle.cleanup(res.session)

    def test_cleanup_missing_path_and_branch(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        ghost = SandboxSession(
            session_id="sbx_ghost",
            target_branch="worktree/sandbox-sbx_ghost",
            sandbox_path=lifecycle.sandbox_base_dir / "sbx_ghost",
            base_commit="0" * 40,
            created_at="2020-01-01T00:00:00+00:00",
        )
        lifecycle.cleanup(ghost)  # must not raise

    def test_include_wip_copies_uncommitted_changes(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        (git_fs.base_path / "f.txt").write_text("dirty\n", encoding="utf-8")
        (git_fs.base_path / "new.txt").write_text("untracked\n", encoding="utf-8")

        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        clean = lifecycle.create(session_id="sbx_nowip")
        assert clean.ok and clean.session is not None
        assert clean.session.wip_applied is False
        assert (clean.session.sandbox_path / "f.txt").read_text(encoding="utf-8") == "x\n"
        assert not (clean.session.sandbox_path / "new.txt").exists()
        lifecycle.cleanup(clean.session)

        wip = lifecycle.create(session_id="sbx_wip", include_wip=True)
        assert wip.ok and wip.session is not None
        assert wip.session.wip_applied is True
        assert "f.txt" in wip.session.wip_paths
        assert "new.txt" in wip.session.wip_paths
        assert (wip.session.sandbox_path / "f.txt").read_text(encoding="utf-8") == "dirty\n"
        assert (wip.session.sandbox_path / "new.txt").read_text(encoding="utf-8") == "untracked\n"
        lifecycle.cleanup(wip.session)

    def test_include_wip_deletes_removed_tracked_file(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        (git_fs.base_path / "f.txt").unlink()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        result = lifecycle.create(session_id="sbx_del", include_wip=True)
        assert result.ok and result.session is not None
        assert "f.txt" in result.session.wip_paths
        assert not (result.session.sandbox_path / "f.txt").exists()
        lifecycle.cleanup(result.session)

    def test_persists_active_row_on_create(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        result = lifecycle.create(session_id="sbx_db1", name="persist-me")
        assert result.ok and result.session is not None
        assert result.warnings == []
        row = self.db.sandboxes.get("sbx_db1")
        assert row is not None
        assert row.status == SandboxStatus.ACTIVE
        assert row.name == "persist-me"
        assert row.branch_name == result.session.target_branch
        assert row.base_commit == result.session.base_commit
        assert row.sandbox_path == result.session.sandbox_path
        lifecycle.cleanup(result.session)

    def test_marks_cleaned_on_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_db2")
        assert res.ok and res.session is not None
        assert self.db.sandboxes.get("sbx_db2") is not None
        lifecycle.cleanup(res.session)
        row = self.db.sandboxes.get("sbx_db2")
        assert row is not None
        assert row.status == SandboxStatus.CLEANED

    def test_cleanup_with_sandbox_record(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_rec")
        assert res.ok and res.session is not None
        row = self.db.sandboxes.get("sbx_rec")
        assert row is not None
        warnings = lifecycle.cleanup(row)
        assert warnings == []
        assert not res.session.sandbox_path.exists()
        updated_row = self.db.sandboxes.get("sbx_rec")
        assert updated_row is not None
        assert updated_row.status == SandboxStatus.CLEANED

    def test_cleanup_warnings_on_db_failure(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_dbfail")
        assert res.ok and res.session is not None

        with patch.object(self.db.sandboxes, "update_status", side_effect=RuntimeError("db error")):
            warnings = lifecycle.cleanup(res.session)
        assert len(warnings) == 1
        assert "Failed to update database status to 'cleaned'" in warnings[0]

    def test_cleanup_warnings_on_worktree_remove_failure(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_rmfail")
        assert res.ok and res.session is not None

        with (
            patch("worktree.core.git.runner.GitRunner.worktree_remove", side_effect=RuntimeError("git wt failed")),
            patch("shutil.rmtree", side_effect=OSError("permission denied")),
        ):
            warnings = lifecycle.cleanup(res.session)
        assert any("Failed to remove sandbox worktree directory" in w for w in warnings)

    def test_cleanup_warnings_on_branch_delete_unexpected_error(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        res = lifecycle.create(session_id="sbx_brfail")
        assert res.ok and res.session is not None

        with patch(
            "worktree.core.git.runner.GitRunner.branch_delete", side_effect=RuntimeError("fatal git branch error")
        ):
            warnings = lifecycle.cleanup(res.session)
        assert any("Failed to delete branch" in w for w in warnings)


def test_wip_helpers(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "mod.txt").write_text("mod\n", encoding="utf-8")
    assert "mod.txt" in list_wip_paths(tmp_path)

    dest = tmp_path / "dest"
    dest.mkdir()
    copy_wip_file(tmp_path, dest, "mod.txt")
    assert (dest / "mod.txt").read_text(encoding="utf-8") == "mod\n"

    # Overlay into existing dir
    sbx = tmp_path / "sbx"
    sbx.mkdir()
    touched = apply_wip_to_sandbox(source_root=tmp_path, sandbox_path=sbx)
    assert "mod.txt" in touched
    assert (sbx / "mod.txt").read_text(encoding="utf-8") == "mod\n"
