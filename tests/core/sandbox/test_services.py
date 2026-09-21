from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder
from worktree.common.constants import DEFAULT_MAXIMUM_SANDBOXES_ALLOWED
from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.models import (
    SandboxCreateStatus,
)
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle


@pytest.fixture
def sandbox_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace with Git and SQLite DB."""
    return WorkspaceBuilder(tmp_path / "sandbox_ws").with_git().with_database().build()


class SandboxCreationTests:
    """Integration tests verifying worktree creation and metadata recording."""

    def test_create_initializes_worktree_and_branch_metadata(
        self,
        sandbox_workspace: Path,
    ) -> None:
        """Create initializes worktree on disk, git branch, and DB row."""
        db = SandboxesRepository(sandbox_workspace)
        lifecycle = SandboxLifecycle(sandbox_workspace, db)

        result = lifecycle.create(session_id="sbx_test001", name="test-sandbox")

        expected_sandbox_path = (sandbox_workspace / ".worktree" / "sandboxes" / "sbx_test001").resolve()
        expected_branch = "worktree/sandbox-sbx_test001"
        head_commit = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")

        assert result.status == SandboxCreateStatus.OK
        assert result.session is not None
        assert result.session.session_id == "sbx_test001"
        assert result.session.target_branch == expected_branch
        assert result.session.sandbox_path == expected_sandbox_path
        assert result.session.base_commit == head_commit
        assert result.session.name == "test-sandbox"
        assert result.session.created_at is not None
        assert result.session.command_passed is None
        assert result.session.wip_applied is False
        assert result.session.wip_paths == []
        assert result.warnings == []
        assert result.errors == []
        assert result.fixes == []
        assert expected_sandbox_path.is_dir()
        assert expected_branch in GitRunner.list_branches(sandbox_workspace)

        record = db.get("sbx_test001")
        assert record is not None
        assert record.id == "sbx_test001"
        assert record.name == "test-sandbox"
        assert record.branch_name == expected_branch
        assert record.base_commit == head_commit
        assert record.sandbox_path == expected_sandbox_path
        assert record.status == SandboxStatus.ACTIVE
        assert record.created_at is not None
        assert record.updated_at is not None


class SandboxCapacityTests:
    """Integration tests verifying capacity ceiling enforcement."""

    def test_create_enforces_max_active_sandboxes_limit(
        self,
        sandbox_workspace: Path,
    ) -> None:
        """Creating a sandbox beyond max_active_sandboxes returns CAPACITY_EXCEEDED."""
        db = SandboxesRepository(sandbox_workspace)
        lifecycle = SandboxLifecycle(sandbox_workspace, db)

        assert DEFAULT_MAXIMUM_SANDBOXES_ALLOWED >= 1
        for idx in range(DEFAULT_MAXIMUM_SANDBOXES_ALLOWED):
            lifecycle.create(f"sbx_cap_{idx + 1}")

        overflow_id = f"sbx_cap_{DEFAULT_MAXIMUM_SANDBOXES_ALLOWED + 1}"
        overflow = lifecycle.create(overflow_id)

        assert overflow.status == SandboxCreateStatus.CAPACITY_EXCEEDED
        assert overflow.session is None
        assert overflow.errors == [
            f"Maximum active sandboxes reached ({DEFAULT_MAXIMUM_SANDBOXES_ALLOWED}/{DEFAULT_MAXIMUM_SANDBOXES_ALLOWED})."
        ]
        assert overflow.warnings == []
        assert overflow.fixes == [
            "Run `wt prune` to remove stale sandboxes, or",
            "Raise sandbox.max_active_sandboxes in .worktree/config.json",
        ]
        assert not (sandbox_workspace / ".worktree" / "sandboxes" / overflow_id).exists()
        assert f"worktree/sandbox-{overflow_id}" not in GitRunner.list_branches(sandbox_workspace)
        assert db.get(overflow_id) is None
