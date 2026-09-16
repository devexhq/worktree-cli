from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.assertions import assert_model_equal
from tests.harness.builders import WorkspaceBuilder
from worktree.core.db import SandboxesRepository, SandboxRecord, SandboxStatus
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.patch import SandboxPatch, extract_conflicts

pytestmark = pytest.mark.integration


@pytest.fixture
def sandbox_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace with Git and SQLite DB."""
    return WorkspaceBuilder(tmp_path / "sandbox_ws").with_git().with_database().build()


class SandboxConflictExtractionTests:
    """Integration tests verifying git apply stderr line parsing."""

    @pytest.mark.parametrize(
        ("stderr_input", "expected_conflicts"),
        [
            pytest.param(
                "error: patch failed: src/main.py:12\nerror: src/main.py: patch does not apply",
                ["src/main.py"],
                id="patch_failed_and_does_not_apply",
            ),
            pytest.param(
                "error: cannot apply binary patch to 'assets/logo.png' without full index line",
                ["assets/logo.png"],
                id="binary_patch_failure",
            ),
            pytest.param(
                "error: new_file.txt: already exists in working directory\nerror: deleted_file.txt: does not exist in index",
                ["deleted_file.txt", "new_file.txt"],
                id="already_exists_and_not_in_index",
            ),
            pytest.param(
                "error: patch failed: a.py:1\nerror: patch failed: b.py:5\nerror: a.py: patch does not apply",
                ["a.py", "b.py"],
                id="multiline_deduplication",
            ),
            pytest.param(
                "",
                [],
                id="empty_stderr",
            ),
        ],
    )
    def test_extract_conflicts_parses_git_apply_stderr_lines(
        self,
        stderr_input: str,
        expected_conflicts: list[str],
    ) -> None:
        """Extract conflicting file paths from varied git apply stderr output lines."""
        assert extract_conflicts(stderr_input) == expected_conflicts


class SandboxApplyRollbackTests:
    """Integration tests verifying working tree rollback on conflict during patch apply."""

    def test_sandbox_patch_apply_rolls_back_partial_changes_on_conflict(
        self,
        sandbox_workspace: Path,
    ) -> None:
        """Conflict during patch application rolls back partial changes and preserves working tree."""
        db = SandboxesRepository(sandbox_workspace)
        lifecycle = SandboxLifecycle(sandbox_workspace, db)
        patch_service = SandboxPatch(sandbox_workspace, db, lifecycle=lifecycle)

        (sandbox_workspace / "target.py").write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        GitRunner.add_all(sandbox_workspace)
        GitRunner.commit(sandbox_workspace, "Add target.py")
        initial_commit = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")

        create_result = lifecycle.create(session_id="sbx_conflict")
        expected_create_session = SandboxSession(
            session_id="sbx_conflict",
            target_branch="worktree/sandbox-sbx_conflict",
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_conflict").resolve(),
            base_commit=initial_commit,
            name=None,
            created_at="DETERMINISTIC_TIMESTAMP_PLACEHOLDER",
            command_passed=None,
            wip_applied=False,
            wip_paths=[],
        )
        expected_create_result = SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=expected_create_session,
            warnings=[],
            errors=[],
            fixes=[],
        )
        assert_model_equal(create_result, expected_create_result, exclude={"session": {"created_at"}})
        assert create_result.session is not None and create_result.session.created_at != ""

        sandbox_dir = sandbox_workspace / ".worktree" / "sandboxes" / "sbx_conflict"
        (sandbox_dir / "target.py").write_text("line 1\nsandbox edit\nline 3\n", encoding="utf-8")
        GitRunner.add_all(sandbox_dir)
        GitRunner.commit(sandbox_dir, "Sandbox change to target.py")

        (sandbox_workspace / "target.py").write_text("line 1\nconflicting main edit\nline 3\n", encoding="utf-8")
        GitRunner.add_all(sandbox_workspace)
        GitRunner.commit(sandbox_workspace, "Main change causing conflict")

        initial_tree = (sandbox_workspace / "target.py").read_text(encoding="utf-8")

        result = patch_service.apply("sbx_conflict")

        expected_result = SandboxApplyResult(
            status=SandboxApplyStatus.CONFLICT,
            sandbox_id="sbx_conflict",
            strategy=SandboxApplyStrategy.PATCH,
            touched_files=[],
            conflicting_files=["target.py"],
            cleaned_up=False,
            commit_sha=None,
            errors=["Cannot apply sandbox sbx_conflict: conflicts detected.\nConflicting files:\n  • target.py"],
            warnings=[],
            fixes=[
                "Inspect sandbox differences with `wt sandbox diff sbx_conflict`",
                "Resolve conflicts in the main workspace or sandbox worktree",
            ],
        )
        assert_model_equal(result, expected_result)
        assert (sandbox_workspace / "target.py").read_text(encoding="utf-8") == initial_tree

        expected_record = SandboxRecord(
            id="sbx_conflict",
            name=None,
            branch_name="worktree/sandbox-sbx_conflict",
            base_commit=initial_commit,
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_conflict").resolve(),
            status=SandboxStatus.CONFLICT,
        )
        record = db.get("sbx_conflict")
        assert record is not None
        assert_model_equal(record, expected_record, exclude={"created_at", "updated_at"})
        assert record.created_at is not None and record.updated_at is not None
