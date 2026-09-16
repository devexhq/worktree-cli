from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder
from tests.harness.matchers import ANY_GIT_SHA, ANY_TIMESTAMP, assert_model_equal
from worktree.core.db import SandboxesRepository, SandboxRecord, SandboxStatus
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateStatus,
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
        assert create_result.status == SandboxCreateStatus.OK

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

        expected_result = SandboxApplyResult.model_construct(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_squash",
            strategy=SandboxApplyStrategy.SQUASH,
            touched_files=["feature1.py", "feature2.py"],
            conflicting_files=[],
            cleaned_up=False,
            commit_sha=ANY_GIT_SHA,
            errors=[],
            warnings=[],
            fixes=[],
        )
        assert_model_equal(result, expected_result)
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
        assert create_result.status == SandboxCreateStatus.OK

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

        expected_result = SandboxApplyResult.model_construct(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_squash_del",
            strategy=SandboxApplyStrategy.SQUASH,
            touched_files=["feature.py"],
            conflicting_files=[],
            cleaned_up=True,
            commit_sha=ANY_GIT_SHA,
            errors=[],
            warnings=[],
            fixes=[],
        )
        assert_model_equal(result, expected_result)
        assert "worktree/sandbox-sbx_squash_del" not in GitRunner.list_branches(sandbox_workspace)
        assert not (sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del").exists()

        expected_record = SandboxRecord.model_construct(
            id="sbx_squash_del",
            name=None,
            branch_name="worktree/sandbox-sbx_squash_del",
            base_commit=initial_commit,
            sandbox_path=(sandbox_workspace / ".worktree" / "sandboxes" / "sbx_squash_del").resolve(),
            status=SandboxStatus.MERGED,
            created_at=ANY_TIMESTAMP,
            updated_at=ANY_TIMESTAMP,
        )
        record = db.get("sbx_squash_del")
        assert record is not None
        assert_model_equal(record, expected_record)
