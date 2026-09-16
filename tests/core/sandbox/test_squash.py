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
from worktree.core.sandbox.services.patch import SandboxPatch

pytestmark = pytest.mark.integration


@pytest.fixture
def sandbox_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace with Git and SQLite DB."""
    return WorkspaceBuilder(tmp_path / "sandbox_ws").with_git().with_database().build()


class SandboxSquashApplyTests:
    """Integration tests verifying squash apply strategy and branch cleanup."""

    def test_squash_apply_collapses_multiple_commits_into_single_commit(
        self,
        sandbox_workspace: Path,
    ) -> None:
        """Squash strategy collapses multiple intermediate sandbox commits into single commit with message."""
        db = SandboxesRepository(sandbox_workspace)
        lifecycle = SandboxLifecycle(sandbox_workspace, db)
        patch_service = SandboxPatch(sandbox_workspace, db, lifecycle=lifecycle)

        head_before = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")

        create_result = lifecycle.create(session_id="sbx_squash")
        expected_create_session = SandboxSession(
            session_id="sbx_squash",
            target_branch="worktree/sandbox-sbx_squash",
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash").resolve(),
            base_commit=head_before,
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

        sandbox_dir = sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash"

        (sandbox_dir / "feature1.py").write_text("feature 1\n", encoding="utf-8")
        GitRunner.add_all(sandbox_dir)
        GitRunner.commit(sandbox_dir, "Commit 1 in sandbox")

        (sandbox_dir / "feature2.py").write_text("feature 2\n", encoding="utf-8")
        GitRunner.add_all(sandbox_dir)
        GitRunner.commit(sandbox_dir, "Commit 2 in sandbox")

        result = patch_service.apply(
            "sbx_squash",
            strategy=SandboxApplyStrategy.SQUASH,
            message="Squash sandbox feature",
        )

        expected_result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_squash",
            strategy=SandboxApplyStrategy.SQUASH,
            touched_files=["feature1.py", "feature2.py"],
            conflicting_files=[],
            cleaned_up=False,
            commit_sha="DETERMINISTIC_SHA_PLACEHOLDER",
            errors=[],
            warnings=[],
            fixes=[],
        )
        assert_model_equal(result, expected_result, exclude={"commit_sha"})
        assert result.commit_sha is not None and len(result.commit_sha) == 40
        assert GitRunner.rev_parse(sandbox_workspace, rev="HEAD") == result.commit_sha
        assert GitRunner.run(["log", "-1", "--format=%B"], sandbox_workspace).strip() == "Squash sandbox feature"
        assert GitRunner.rev_parse(sandbox_workspace, rev="HEAD~1") == head_before
        assert (sandbox_workspace / "feature1.py").read_text(encoding="utf-8") == "feature 1\n"
        assert (sandbox_workspace / "feature2.py").read_text(encoding="utf-8") == "feature 2\n"

    def test_squash_apply_deletes_sandbox_branch_and_marks_applied(
        self,
        sandbox_workspace: Path,
    ) -> None:
        """Squash apply with delete=True deletes sandbox branch, worktree directory, and marks sandbox merged."""
        db = SandboxesRepository(sandbox_workspace)
        lifecycle = SandboxLifecycle(sandbox_workspace, db)
        patch_service = SandboxPatch(sandbox_workspace, db, lifecycle=lifecycle)

        initial_commit = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")

        create_result = lifecycle.create(session_id="sbx_squash_del")
        expected_create_session = SandboxSession(
            session_id="sbx_squash_del",
            target_branch="worktree/sandbox-sbx_squash_del",
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del").resolve(),
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

        sandbox_dir = sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del"

        (sandbox_dir / "feature.py").write_text("squash feature\n", encoding="utf-8")
        GitRunner.add_all(sandbox_dir)
        GitRunner.commit(sandbox_dir, "Add feature in sandbox")

        result = patch_service.apply(
            "sbx_squash_del",
            strategy=SandboxApplyStrategy.SQUASH,
            delete=True,
            message="Squash and cleanup",
        )

        expected_result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_squash_del",
            strategy=SandboxApplyStrategy.SQUASH,
            touched_files=["feature.py"],
            conflicting_files=[],
            cleaned_up=True,
            commit_sha="DETERMINISTIC_SHA_PLACEHOLDER",
            errors=[],
            warnings=[],
            fixes=[],
        )
        assert_model_equal(result, expected_result, exclude={"commit_sha"})
        assert result.commit_sha is not None and len(result.commit_sha) == 40
        assert "worktree/sandbox-sbx_squash_del" not in GitRunner.list_branches(sandbox_workspace)
        assert not (sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del").exists()

        expected_record = SandboxRecord(
            id="sbx_squash_del",
            name=None,
            branch_name="worktree/sandbox-sbx_squash_del",
            base_commit=initial_commit,
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del").resolve(),
            status=SandboxStatus.MERGED,
        )
        record = db.get("sbx_squash_del")
        assert record is not None
        assert_model_equal(record, expected_record, exclude={"created_at", "updated_at"})
        assert record.created_at is not None and record.updated_at is not None
