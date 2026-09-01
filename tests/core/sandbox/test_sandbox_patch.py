"""Tests for SandboxPatch service."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch as mock_patch

import pytest

from tests.helpers import GitFileSystem
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.sandbox import (
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxDiffStatus,
)
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.patch import SandboxPatch


class TestSandboxPatch:
    """Integration tests for diff and apply operations on sandboxes."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path)

    def test_apply_sandbox_patch_strategy_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_app1")
        assert res.ok and res.session is not None
        session = res.session

        # Make modifications in the sandbox
        (session.sandbox_path / "new_file.py").write_text("print('hello')\n", encoding="utf-8")
        (session.sandbox_path / "f.txt").write_text("modified in sandbox\n", encoding="utf-8")

        result = patch.apply(session.session_id, strategy=SandboxApplyStrategy.PATCH)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert result.strategy == SandboxApplyStrategy.PATCH
        assert set(result.touched_files) == {"new_file.py", "f.txt"}
        assert (git_fs.base_path / "new_file.py").read_text(encoding="utf-8") == "print('hello')\n"
        assert (git_fs.base_path / "f.txt").read_text(encoding="utf-8") == "modified in sandbox\n"

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.MERGED
        lifecycle.cleanup(session)

    def test_apply_sandbox_squash_strategy_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_sq")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "feature.py").write_text("def feat(): pass\n", encoding="utf-8")

        result = patch.apply(
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
        lifecycle.cleanup(session)

    def test_apply_sandbox_with_delete_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_del")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "del_test.txt").write_text("abc\n", encoding="utf-8")

        result = patch.apply(session.session_id, delete=True)
        assert result.ok
        assert result.cleaned_up
        assert result.warnings == []
        assert not session.sandbox_path.exists()

        branch_proc = subprocess.run(
            ["git", "branch", "--list", session.target_branch],
            cwd=git_fs.base_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert session.target_branch not in branch_proc.stdout

    def test_apply_sandbox_with_delete_cleanup_propagates_warnings(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes, lifecycle=lifecycle)

        res = lifecycle.create(session_id="sbx_del_warn")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "del_warn.txt").write_text("abc\n", encoding="utf-8")

        with mock_patch.object(lifecycle, "cleanup", return_value=["partial cleanup warning"]):
            result = patch.apply(session.session_id, delete=True)
        assert result.ok
        assert result.cleaned_up
        assert "partial cleanup warning" in result.warnings
        lifecycle.cleanup(session)

    def test_apply_sandbox_merged_status_update_failure_warning(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_merged_fail")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "f.txt").write_text("apply without db\n", encoding="utf-8")

        with mock_patch.object(self.db.sandboxes, "update_status", side_effect=RuntimeError("db lock")):
            result = patch.apply(session.session_id)
        assert result.ok
        assert any("Failed to update database status to 'merged'" in w for w in result.warnings)
        lifecycle.cleanup(session)

    def test_apply_sandbox_main_repo_dirty_aborts(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_dirty")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "a.txt").write_text("a\n", encoding="utf-8")

        # Make main workspace dirty
        (git_fs.base_path / "f.txt").write_text("dirty in main\n", encoding="utf-8")

        result = patch.apply(session.session_id, allow_dirty=False)
        assert not result.ok
        assert result.status == SandboxApplyStatus.MAIN_REPO_DIRTY
        assert "uncommitted changes" in result.errors[0]

        # Reset main repo for cleanup
        subprocess.run(["git", "checkout", "--", "f.txt"], cwd=git_fs.base_path, check=True, capture_output=True)
        lifecycle.cleanup(session)

    def test_apply_sandbox_main_repo_dirty_allowed(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_allow_dirty")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "other.txt").write_text("other\n", encoding="utf-8")

        # Make main workspace dirty in unrelated file
        (git_fs.base_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        result = patch.apply(session.session_id, allow_dirty=True)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert (git_fs.base_path / "other.txt").exists()
        lifecycle.cleanup(session)

    def test_apply_sandbox_empty_diff(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_empty")
        assert res.ok and res.session is not None
        session = res.session

        # No changes made in sandbox
        result = patch.apply(session.session_id)
        assert result.status == SandboxApplyStatus.EMPTY_DIFF
        assert not result.touched_files
        lifecycle.cleanup(session)

    def test_apply_sandbox_conflict_detected(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_conf")
        assert res.ok and res.session is not None
        session = res.session

        # Sandbox edits line 1 of f.txt
        (session.sandbox_path / "f.txt").write_text("sandbox line\n", encoding="utf-8")

        # Main workspace commits a conflicting edit to f.txt
        (git_fs.base_path / "f.txt").write_text("main line\n", encoding="utf-8")
        subprocess.run(
            ["git", "commit", "-am", "conflicting commit"], cwd=git_fs.base_path, check=True, capture_output=True
        )

        result = patch.apply(session.session_id, allow_dirty=False)
        assert not result.ok
        assert result.status == SandboxApplyStatus.CONFLICT
        assert "f.txt" in result.conflicting_files

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.CONFLICT
        lifecycle.cleanup(session)

    def test_apply_sandbox_dry_run(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_dry")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "dry.txt").write_text("dry test\n", encoding="utf-8")

        result = patch.apply(session.session_id, dry_run=True)
        assert result.ok
        assert result.status == SandboxApplyStatus.OK
        assert not (git_fs.base_path / "dry.txt").exists()

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.ACTIVE
        lifecycle.cleanup(session)

    def test_apply_sandbox_not_found_and_missing_disk(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res_missing = patch.apply("sbx_nonexistent")
        assert res_missing.status == SandboxApplyStatus.NOT_FOUND

        res = lifecycle.create(session_id="sbx_disk_gone")
        assert res.ok and res.session is not None
        session = res.session
        shutil.rmtree(session.sandbox_path)

        res_disk = patch.apply(session.session_id)
        assert res_disk.status == SandboxApplyStatus.NOT_FOUND

        row = self.db.sandboxes.get(session.session_id)
        assert row is not None
        assert row.status == SandboxStatus.CLEANED

    def test_apply_sandbox_already_merged(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_already")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "f.txt").write_text("merged\n", encoding="utf-8")
        patch.apply(session.session_id)

        # Apply again
        res2 = patch.apply(session.session_id)
        assert res2.status == SandboxApplyStatus.ALREADY_MERGED
        lifecycle.cleanup(session)

    def test_diff_sandbox(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        lifecycle = SandboxLifecycle(path=git_fs.base_path, db=self.db.sandboxes)
        patch = SandboxPatch(path=git_fs.base_path, db=self.db.sandboxes)

        res = lifecycle.create(session_id="sbx_diff")
        assert res.ok and res.session is not None
        session = res.session

        (session.sandbox_path / "diff_test.txt").write_text("hello diff\n", encoding="utf-8")

        diff_res = patch.diff(session.session_id)
        assert diff_res.ok
        assert diff_res.status == SandboxDiffStatus.OK
        assert "diff --git a/diff_test.txt b/diff_test.txt" in diff_res.diff_text
        assert "diff_test.txt" in diff_res.files_changed

        stat_res = patch.diff(session.session_id, stat=True)
        assert stat_res.ok
        assert "diff_test.txt | 1 +" in stat_res.stat_text

        lifecycle.cleanup(session)
