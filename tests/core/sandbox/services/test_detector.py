"""Integration tests for SandboxDetector and stale sandbox classification service."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.harness import (
    AnyMatching,
    DetectionResultBuilder,
    WorkspaceBuilder,
    assert_model_equal,
)
from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.git.exceptions import GitCommandError
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox import Sandbox
from worktree.core.sandbox.models import (
    SandboxDetectionStatus,
    StaleSandboxCategory,
)
from worktree.core.sandbox.services.detector import SandboxDetector, detect_stale_sandboxes


@pytest.fixture
def detector_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace with Git and SQLite DB."""
    return WorkspaceBuilder(tmp_path / "detector_ws").with_git().with_database().build()


class SandboxDetectorBaselineTests:
    """Baseline tests for SandboxDetector on clean workspaces and active sandboxes."""

    def test_detect_clean_workspace_reports_zero_stale(
        self,
        detector_workspace: Path,
    ) -> None:
        """Clean repository with no sandboxes should return OK with 0 stale items."""
        db = SandboxesRepository(detector_workspace)
        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = DetectionResultBuilder().build()
        assert_model_equal(result, expected)

    def test_active_sandbox_is_excluded_from_all_categories(
        self,
        detector_workspace: Path,
    ) -> None:
        """Valid active sandboxes must be recorded in active count and excluded from stale items."""
        db = SandboxesRepository(detector_workspace)
        manager = Sandbox(detector_workspace, db)

        create_result = manager.create(session_id="sbx_active_123")
        assert create_result.ok

        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = DetectionResultBuilder().with_active_sandbox_count(1).build()
        assert_model_equal(result, expected)


class SandboxDetectorCategoryTests:
    """Category-specific tests for worktree refs, orphaned directories, DB records, and branches."""

    def test_stale_worktree_ref_is_detected(
        self,
        detector_workspace: Path,
    ) -> None:
        """Stale worktree administrative entries and their unattached branches should be detected."""
        db = SandboxesRepository(detector_workspace)
        target = detector_workspace / ".worktree" / "sandboxes" / "sbx_wt1"
        GitRunner.worktree_add(
            detector_workspace,
            target_path=target,
            branch="worktree/sandbox-sbx_wt1",
            base_ref="main",
        )
        shutil.rmtree(target)

        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_WORKTREE_REF,
                identifier=str(target),
                path=target,
                branch_name="worktree/sandbox-sbx_wt1",
                reason=AnyMatching(r".*gitdir.*", "GIT_PRUNABLE_REASON"),
            )
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier="worktree/sandbox-sbx_wt1",
                branch_name="worktree/sandbox-sbx_wt1",
                reason="Sandbox branch 'worktree/sandbox-sbx_wt1' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result, expected)

    def test_orphaned_directories_classified_by_dirty_state_and_db_status(
        self,
        detector_workspace: Path,
    ) -> None:
        """Orphaned directories should be classified with their dirty state and DB reconciliation reason."""
        db = SandboxesRepository(detector_workspace)
        sandboxes_dir = detector_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        clean_dir = sandboxes_dir / "sbx_clean"
        clean_dir.mkdir()

        dirty_dir = sandboxes_dir / "sbx_dirty"
        GitRunner.worktree_add(
            detector_workspace,
            target_path=dirty_dir,
            branch="worktree/sandbox-sbx_dirty",
            base_ref="main",
        )
        (dirty_dir / "uncommitted.txt").write_text("wip", encoding="utf-8")

        cleaned_dir = sandboxes_dir / "sbx_cleaned"
        cleaned_dir.mkdir()
        db.create(
            id="sbx_cleaned",
            branch_name="worktree/sandbox-sbx_cleaned",
            base_commit="abc",
            sandbox_path=cleaned_dir,
        )
        db.update_status("sbx_cleaned", SandboxStatus.CLEANED)

        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_clean",
                path=clean_dir,
                reason="Sandbox directory 'sbx_clean' is not tracked in the database",
            )
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_cleaned",
                path=cleaned_dir,
                branch_name="worktree/sandbox-sbx_cleaned",
                session_id="sbx_cleaned",
                reason="Sandbox directory 'sbx_cleaned' has database status 'cleaned'",
            )
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_dirty",
                path=dirty_dir,
                is_dirty=True,
                dirty_file_count=1,
                reason="Sandbox directory 'sbx_dirty' is not tracked in the database",
            )
            .build()
        )
        assert_model_equal(result, expected)

    def test_stale_db_record_is_detected(
        self,
        detector_workspace: Path,
    ) -> None:
        """Active database records with missing sandbox directories should be detected."""
        db = SandboxesRepository(detector_workspace)
        missing_path = detector_workspace / ".worktree" / "sandboxes" / "sbx_missing"
        db.create(
            id="sbx_missing",
            branch_name="worktree/sandbox-sbx_missing",
            base_commit="abc",
            sandbox_path=missing_path,
        )

        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_DB_RECORD,
                identifier="sbx_missing",
                path=missing_path,
                branch_name="worktree/sandbox-sbx_missing",
                session_id="sbx_missing",
                reason="Active database record 'sbx_missing' has missing sandbox path on disk",
            )
            .build()
        )
        assert_model_equal(result, expected)

    def test_stale_branch_is_detected(
        self,
        detector_workspace: Path,
    ) -> None:
        """Unattached sandbox branches matching worktree/sandbox-* should be detected."""
        db = SandboxesRepository(detector_workspace)
        branch_name = "worktree/sandbox-sbx_abandoned"
        GitRunner.run(["branch", branch_name], detector_workspace)

        detector = SandboxDetector(detector_workspace, db)

        result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier=branch_name,
                branch_name=branch_name,
                reason=f"Sandbox branch '{branch_name}' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result, expected)


class SandboxDetectorFacadeTests:
    """Tests verifying helper function and Sandbox facade method agree."""

    def test_detect_stale_sandboxes_helper_and_sandbox_facade_agree(
        self,
        detector_workspace: Path,
    ) -> None:
        """Helper and facade methods return equivalent results on clean workspace."""
        db = SandboxesRepository(detector_workspace)
        manager = Sandbox(detector_workspace, db)

        res_helper = detect_stale_sandboxes(detector_workspace, db)
        res_manager = manager.detect()

        expected = DetectionResultBuilder().build()
        assert_model_equal(res_helper, expected)
        assert_model_equal(res_manager, expected)


class SandboxDetectorFailureTests:
    """Tests verifying error handling when git or database operations fail."""

    def test_detect_returns_git_failed_on_worktree_list_error(
        self,
        detector_workspace: Path,
    ) -> None:
        """When GitRunner.worktree_list fails with GitCommandError, status should be GIT_FAILED."""
        db = SandboxesRepository(detector_workspace)
        detector = SandboxDetector(detector_workspace, db)

        with patch.object(
            GitRunner,
            "worktree_list",
            side_effect=GitCommandError(["git", "worktree", "list"], 1, "", "fatal error"),
        ):
            result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_status(SandboxDetectionStatus.GIT_FAILED)
            .with_errors(
                "Failed to list git worktrees (GIT_FAILED): Git execution failed ('git git worktree list'): fatal error"
            )
            .build()
        )
        assert_model_equal(result, expected)

    def test_detect_returns_error_on_database_failure(
        self,
        detector_workspace: Path,
    ) -> None:
        """When database listing fails, status should be ERROR with description."""
        db = SandboxesRepository(detector_workspace)
        detector = SandboxDetector(detector_workspace, db)

        with patch.object(db, "list", side_effect=RuntimeError("database locked")):
            result = detector.detect()

        expected = (
            DetectionResultBuilder()
            .with_status(SandboxDetectionStatus.ERROR)
            .with_errors("Failed to query sandboxes from database: database locked")
            .build()
        )
        assert_model_equal(result, expected)
