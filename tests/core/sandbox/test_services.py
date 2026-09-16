from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder
from tests.harness.matchers import ANY_ISO_TIMESTAMP, ANY_TIMESTAMP, assert_model_equal
from worktree.common.constants import DEFAULT_MAXIMUM_SANDBOXES_ALLOWED
from worktree.core.db import SandboxesRepository, SandboxRecord, SandboxStatus
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.models import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle

pytestmark = pytest.mark.integration


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

        expected_session = SandboxSession.model_construct(
            session_id="sbx_test001",
            target_branch=expected_branch,
            sandbox_path=expected_sandbox_path,
            base_commit=head_commit,
            name="test-sandbox",
            created_at=ANY_ISO_TIMESTAMP,
            command_passed=None,
            wip_applied=False,
            wip_paths=[],
        )
        expected_result = SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=expected_session,
            warnings=[],
            errors=[],
            fixes=[],
        )
        assert_model_equal(result, expected_result)
        assert expected_sandbox_path.is_dir()
        assert expected_branch in GitRunner.list_branches(sandbox_workspace)

        record = db.get("sbx_test001")
        assert record is not None
        expected_record = SandboxRecord.model_construct(
            id="sbx_test001",
            name="test-sandbox",
            branch_name=expected_branch,
            base_commit=head_commit,
            sandbox_path=expected_sandbox_path,
            status=SandboxStatus.ACTIVE,
            created_at=ANY_TIMESTAMP,
            updated_at=ANY_TIMESTAMP,
        )
        assert_model_equal(record, expected_record)


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

        expected_overflow = SandboxCreateResult(
            status=SandboxCreateStatus.CAPACITY_EXCEEDED,
            session=None,
            errors=[
                f"Maximum active sandboxes reached ({DEFAULT_MAXIMUM_SANDBOXES_ALLOWED}/{DEFAULT_MAXIMUM_SANDBOXES_ALLOWED})."
            ],
            warnings=[],
            fixes=[
                "Run `wt prune` to remove stale sandboxes, or",
                "Raise sandbox.max_active_sandboxes in .worktree/config.json",
            ],
        )
        assert_model_equal(overflow, expected_overflow)
        assert not (sandbox_workspace / ".worktree" / "sandboxes" / overflow_id).exists()
        assert f"worktree/sandbox-{overflow_id}" not in GitRunner.list_branches(sandbox_workspace)
        assert db.get(overflow_id) is None
