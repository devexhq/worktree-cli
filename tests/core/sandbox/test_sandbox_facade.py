"""Tests for Sandbox coordinator facade."""

from __future__ import annotations

import pytest

from tests.helpers import GitFileSystem
from worktree.core.db import WorktreeDb
from worktree.core.sandbox import (
    Sandbox,
    SandboxApplyStatus,
    SandboxCreateStatus,
    SandboxDiffStatus,
)


class TestSandboxFacade:
    """Facade tests for Sandbox coordinating lifecycle and patch services."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path)

    def test_sandbox_facade_full_flow(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        sandbox = Sandbox(path=git_fs.base_path, db=self.db.sandboxes)

        assert sandbox.config is None
        assert sandbox.sandbox_base_dir == (git_fs.base_path / ".worktree" / "sandboxes").resolve()
        assert sandbox.get_active() == []

        create_res = sandbox.create(session_id="sbx_mgr")
        assert create_res.ok
        assert create_res.status == SandboxCreateStatus.OK
        assert create_res.session is not None
        assert sandbox.config is not None
        assert sandbox.get_active() == [create_res.session.sandbox_path]

        (create_res.session.sandbox_path / "hello.py").write_text("print(1)\n", encoding="utf-8")

        diff_res = sandbox.diff(create_res.session.session_id)
        assert diff_res.ok
        assert diff_res.status == SandboxDiffStatus.OK

        apply_res = sandbox.apply(create_res.session.session_id, delete=True)
        assert apply_res.ok
        assert apply_res.status == SandboxApplyStatus.OK
        assert apply_res.cleaned_up

        sandbox.prune_git_worktrees()
        assert sandbox.get_active() == []

    def test_cleanup_sandbox_with_record(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        sandbox = Sandbox(path=git_fs.base_path, db=self.db.sandboxes)
        create_res = sandbox.create(session_id="sbx_mgr_rec")
        assert create_res.ok and create_res.session is not None

        row = self.db.sandboxes.get("sbx_mgr_rec")
        assert row is not None
        warnings = sandbox.cleanup(row)
        assert warnings == []
        assert not create_res.session.sandbox_path.exists()

    def test_detect_stale_sandboxes(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        sandbox = Sandbox(path=git_fs.base_path, db=self.db.sandboxes)
        detect_res = sandbox.detect()
        assert detect_res.ok
        assert detect_res.total_stale_count == 0

    def test_list_and_show_and_delete(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        sandbox = Sandbox(path=git_fs.base_path, db=self.db.sandboxes)
        create_res = sandbox.create(session_id="sbx_list_test")
        assert create_res.ok

        list_res = sandbox.list()
        assert list_res.ok
        assert any(s.id == "sbx_list_test" for s in list_res.sandboxes)

        show_res = sandbox.show("sbx_list_test")
        assert show_res.ok
        assert show_res.sandbox is not None
        assert show_res.sandbox.id == "sbx_list_test"

        del_res = sandbox.delete("sbx_list_test")
        assert del_res.ok
