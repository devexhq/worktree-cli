"""Tests for GitSandboxManager coordinator facade."""

from __future__ import annotations

import pytest

from tests.helpers import GitFileSystem
from worktree.core.db import WorktreeDb
from worktree.core.sandbox import (
    GitSandboxManager,
    SandboxApplyStatus,
    SandboxCreateStatus,
    SandboxDiffStatus,
)


class TestGitSandboxManager:
    """Facade tests for GitSandboxManager coordinating lifecycle and patch services."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path)

    def test_manager_full_flow(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path, db=self.db.sandboxes)

        assert manager.config is None
        assert manager.sandbox_base_dir == (git_fs.base_path / ".worktree" / "sandboxes").resolve()
        assert manager.get_active_sandboxes() == []

        create_res = manager.create_sandbox(session_id="sbx_mgr")
        assert create_res.ok
        assert create_res.status == SandboxCreateStatus.OK
        assert create_res.session is not None
        assert manager.config is not None
        assert manager.get_active_sandboxes() == [create_res.session.sandbox_path]

        (create_res.session.sandbox_path / "hello.py").write_text("print(1)\n", encoding="utf-8")

        diff_res = manager.diff_sandbox(create_res.session.session_id)
        assert diff_res.ok
        assert diff_res.status == SandboxDiffStatus.OK

        apply_res = manager.apply_sandbox(create_res.session.session_id, delete=True)
        assert apply_res.ok
        assert apply_res.status == SandboxApplyStatus.OK
        assert apply_res.cleaned_up

        manager.prune()
        assert manager.get_active_sandboxes() == []

    def test_cleanup_sandbox_with_record(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        manager = GitSandboxManager(path=git_fs.base_path, db=self.db.sandboxes)
        create_res = manager.create_sandbox(session_id="sbx_mgr_rec")
        assert create_res.ok and create_res.session is not None

        row = self.db.sandboxes.get("sbx_mgr_rec")
        assert row is not None
        warnings = manager.cleanup_sandbox(row)
        assert warnings == []
        assert not create_res.session.sandbox_path.exists()
