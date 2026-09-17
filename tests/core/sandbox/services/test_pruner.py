"""Integration tests for SandboxPruner and safe prune execution service."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.harness import (
    ANY_TIMESTAMP,
    AnyMatching,
    PruneResultBuilder,
    WorkspaceBuilder,
    assert_model_equal,
)
from worktree.common.lock import LockTimeoutError
from worktree.core.db import SandboxesRepository, SandboxRecord, SandboxStatus
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox import Sandbox
from worktree.core.sandbox.models import (
    PruneAction,
    SandboxDetectionResult,
    SandboxDetectionStatus,
    SandboxPruneStatus,
    StaleSandboxCategory,
)
from worktree.core.sandbox.services.pruner import SandboxPruner, prune_stale_sandboxes


@pytest.fixture
def pruner_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace with Git and SQLite DB."""
    return WorkspaceBuilder(tmp_path / "pruner_ws").with_git().with_database().build()


class SandboxPrunerBaselineTests:
    """Baseline tests for SandboxPruner on clean or simulated workspaces."""

    def test_prune_clean_workspace_is_a_noop(self, pruner_workspace: Path) -> None:
        """Pruning a clean workspace should return OK with 0 items."""
        db = SandboxesRepository(pruner_workspace)
        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune()

        assert_model_equal(result, PruneResultBuilder().build())

    def test_prune_dry_run_reports_all_categories_without_mutation(
        self,
        pruner_workspace: Path,
    ) -> None:
        """Dry-run reports planned actions across categories without mutating disk, DB, or git."""
        db = SandboxesRepository(pruner_workspace)
        sandboxes_dir = pruner_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        clean_dir = sandboxes_dir / "sbx_clean"
        clean_dir.mkdir()

        dirty_dir = sandboxes_dir / "sbx_dirty"
        GitRunner.worktree_add(
            pruner_workspace,
            target_path=dirty_dir,
            branch="worktree/sandbox-sbx_dirty",
            base_ref="main",
        )
        (dirty_dir / "dirty.txt").write_text("wip", encoding="utf-8")

        missing_path = sandboxes_dir / "sbx_missing"
        db.create(
            id="sbx_missing",
            branch_name="worktree/sandbox-sbx_missing",
            base_commit="abc",
            sandbox_path=missing_path,
        )

        subprocess.run(
            ["git", "branch", "worktree/sandbox-sbx_dead"],
            cwd=pruner_workspace,
            check=True,
            capture_output=True,
        )

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune(dry_run=True, force=False)

        expected = (
            PruneResultBuilder()
            .with_dry_run(True)
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_clean",
                action=PruneAction.PRUNED,
                path=clean_dir,
                reason="Would prune: Sandbox directory 'sbx_clean' is not tracked in the database",
            )
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_dirty",
                action=PruneAction.SKIPPED,
                path=dirty_dir,
                reason="Orphaned directory 'sbx_dirty' contains uncommitted changes; use --force to delete",
            )
            .with_item(
                category=StaleSandboxCategory.STALE_DB_RECORD,
                identifier="sbx_missing",
                action=PruneAction.PRUNED,
                path=missing_path,
                branch_name="worktree/sandbox-sbx_missing",
                session_id="sbx_missing",
                reason="Would prune: Active database record 'sbx_missing' has missing sandbox path on disk",
            )
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier="worktree/sandbox-sbx_dead",
                action=PruneAction.PRUNED,
                branch_name="worktree/sandbox-sbx_dead",
                reason="Would prune: Sandbox branch 'worktree/sandbox-sbx_dead' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result, expected)
        assert clean_dir.exists()
        assert dirty_dir.exists()
        record = db.get("sbx_missing")
        assert record is not None and record.status == SandboxStatus.ACTIVE
        branches = GitRunner.list_branches(pruner_workspace, pattern="worktree/sandbox-*")
        assert "worktree/sandbox-sbx_dead" in branches


class SandboxPrunerSafetyTests:
    """Safety tests verifying preservation of dirty orphans without force."""

    def test_dirty_orphan_skipped_without_force(self, pruner_workspace: Path) -> None:
        """Dirty orphan directory must be preserved with SKIPPED status when force=False."""
        db = SandboxesRepository(pruner_workspace)
        sandboxes_dir = pruner_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dirty_dir = sandboxes_dir / "sbx_dirty_orphan"
        GitRunner.worktree_add(
            pruner_workspace,
            target_path=dirty_dir,
            branch="worktree/sandbox-sbx_dirty_orphan",
            base_ref="main",
        )
        (dirty_dir / "wip.txt").write_text("changes", encoding="utf-8")

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune(force=False)

        expected = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_dirty_orphan",
                action=PruneAction.SKIPPED,
                path=dirty_dir,
                reason="Orphaned directory 'sbx_dirty_orphan' contains uncommitted changes; use --force to delete",
            )
            .build()
        )
        assert_model_equal(result, expected)
        assert dirty_dir.exists()

    def test_dirty_orphan_deleted_with_force(self, pruner_workspace: Path) -> None:
        """Dirty orphan directory must be removed when force=True."""
        db = SandboxesRepository(pruner_workspace)
        sandboxes_dir = pruner_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dirty_dir = sandboxes_dir / "sbx_dirty_forced"
        GitRunner.worktree_add(
            pruner_workspace,
            target_path=dirty_dir,
            branch="worktree/sandbox-sbx_dirty_forced",
            base_ref="main",
        )
        (dirty_dir / "wip.txt").write_text("changes", encoding="utf-8")

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune(force=True)

        expected = (
            PruneResultBuilder()
            .with_force(True)
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_dirty_forced",
                action=PruneAction.PRUNED,
                path=dirty_dir,
                reason="Sandbox directory 'sbx_dirty_forced' is not tracked in the database",
            )
            .build()
        )
        assert_model_equal(result, expected)
        assert not dirty_dir.exists()

    def test_clean_orphan_deleted_without_force(self, pruner_workspace: Path) -> None:
        """Clean orphan directory must be deleted even with force=False."""
        db = SandboxesRepository(pruner_workspace)
        sandboxes_dir = pruner_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        clean_dir = sandboxes_dir / "sbx_clean_orphan"
        clean_dir.mkdir()

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune(force=False)

        expected = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_clean_orphan",
                action=PruneAction.PRUNED,
                path=clean_dir,
                reason="Sandbox directory 'sbx_clean_orphan' is not tracked in the database",
            )
            .build()
        )
        assert_model_equal(result, expected)
        assert not clean_dir.exists()


class SandboxPrunerCategoryTests:
    """Category-specific tests for worktree refs, DB records, and branches."""

    def test_stale_worktree_ref_is_pruned(self, pruner_workspace: Path) -> None:
        """Stale worktree administrative entries should be pruned."""
        db = SandboxesRepository(pruner_workspace)
        target = pruner_workspace / ".worktree" / "sandboxes" / "sbx_stale_wt"
        GitRunner.worktree_add(
            pruner_workspace,
            target_path=target,
            branch="worktree/sandbox-sbx_stale_wt",
            base_ref="main",
        )
        shutil.rmtree(target)

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune()

        expected = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_WORKTREE_REF,
                identifier=str(target),
                action=PruneAction.PRUNED,
                path=target,
                branch_name="worktree/sandbox-sbx_stale_wt",
                reason=AnyMatching(r".*gitdir.*", "GIT_PRUNABLE_REASON"),
            )
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier="worktree/sandbox-sbx_stale_wt",
                action=PruneAction.PRUNED,
                branch_name="worktree/sandbox-sbx_stale_wt",
                reason="Sandbox branch 'worktree/sandbox-sbx_stale_wt' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result, expected)

    def test_stale_db_record_is_reconciled_to_cleaned(self, pruner_workspace: Path) -> None:
        """Active DB records with missing paths must be updated to CLEANED."""
        db = SandboxesRepository(pruner_workspace)
        missing_path = pruner_workspace / ".worktree" / "sandboxes" / "sbx_db_stale"
        db.create(
            id="sbx_db_stale",
            branch_name="worktree/sandbox-sbx_db_stale",
            base_commit="abc",
            sandbox_path=missing_path,
        )

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune()

        expected = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_DB_RECORD,
                identifier="sbx_db_stale",
                action=PruneAction.PRUNED,
                path=missing_path,
                branch_name="worktree/sandbox-sbx_db_stale",
                session_id="sbx_db_stale",
                reason="Active database record 'sbx_db_stale' has missing sandbox path on disk",
            )
            .build()
        )
        assert_model_equal(result, expected)
        record = db.get("sbx_db_stale")
        assert record is not None
        assert_model_equal(
            record,
            SandboxRecord.model_construct(
                id="sbx_db_stale",
                name=None,
                branch_name="worktree/sandbox-sbx_db_stale",
                base_commit="abc",
                sandbox_path=missing_path,
                status=SandboxStatus.CLEANED,
                created_at=ANY_TIMESTAMP,
                updated_at=ANY_TIMESTAMP,
            ),
        )

    def test_stale_branch_is_deleted(self, pruner_workspace: Path) -> None:
        """Stale sandbox temporary branches must be deleted."""
        db = SandboxesRepository(pruner_workspace)
        branch_name = "worktree/sandbox-sbx_stale_branch"
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=pruner_workspace,
            check=True,
            capture_output=True,
        )

        pruner = SandboxPruner(pruner_workspace, db)

        result = pruner.prune()

        expected = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier=branch_name,
                action=PruneAction.PRUNED,
                branch_name=branch_name,
                reason=f"Sandbox branch '{branch_name}' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result, expected)
        branches = GitRunner.list_branches(pruner_workspace, pattern="worktree/sandbox-*")
        assert branch_name not in branches


class SandboxPrunerIdempotencyTests:
    """Tests verifying multi-resource pruning followed by an idempotent re-run."""

    def test_combined_prune_then_idempotent_rerun(self, pruner_workspace: Path) -> None:
        """Pruning multiple categories followed by a second run must be clean and idempotent."""
        db = SandboxesRepository(pruner_workspace)
        sandboxes_dir = pruner_workspace / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dir1 = sandboxes_dir / "sbx_c1"
        dir1.mkdir()
        db.create(
            id="sbx_c1",
            branch_name="worktree/sandbox-sbx_c1",
            base_commit="abc",
            sandbox_path=dir1,
        )
        db.update_status("sbx_c1", SandboxStatus.CLEANED)

        branch_name = "worktree/sandbox-sbx_c2"
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=pruner_workspace,
            check=True,
            capture_output=True,
        )

        manager = Sandbox(pruner_workspace, db)
        create_res = manager.create(session_id="sbx_protected")
        assert create_res.ok

        result1 = manager.prune()

        expected1 = (
            PruneResultBuilder()
            .with_item(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_c1",
                action=PruneAction.PRUNED,
                path=dir1,
                branch_name="worktree/sandbox-sbx_c1",
                session_id="sbx_c1",
                reason="Sandbox directory 'sbx_c1' has database status 'cleaned'",
            )
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier=branch_name,
                action=PruneAction.PRUNED,
                branch_name=branch_name,
                reason=f"Sandbox branch '{branch_name}' is not attached to any active sandbox or worktree",
            )
            .build()
        )
        assert_model_equal(result1, expected1)
        assert not dir1.exists()
        assert (sandboxes_dir / "sbx_protected").exists()

        result2 = manager.prune()

        assert_model_equal(result2, PruneResultBuilder().build())


class SandboxPrunerFacadeTests:
    """Tests verifying helper function and Sandbox facade method agree."""

    def test_prune_stale_sandboxes_helper_and_sandbox_facade_agree(
        self,
        pruner_workspace: Path,
    ) -> None:
        """Helper and facade methods return equivalent results on clean workspace."""
        db = SandboxesRepository(pruner_workspace)
        manager = Sandbox(pruner_workspace, db)

        res_helper = prune_stale_sandboxes(pruner_workspace, db, dry_run=True)
        res_manager = manager.prune(dry_run=True)

        expected = PruneResultBuilder().with_dry_run(True).build()
        assert_model_equal(res_helper, expected)
        assert_model_equal(res_manager, expected)


class SandboxPrunerFailureTests:
    """Tests verifying error handling, detection failures, and lock timeouts."""

    def test_prune_aborts_with_git_failed_when_detection_fails(
        self,
        pruner_workspace: Path,
    ) -> None:
        """When detector returns GIT_FAILED, prune should abort with GIT_FAILED status."""
        db = SandboxesRepository(pruner_workspace)
        pruner = SandboxPruner(pruner_workspace, db)

        with patch.object(
            pruner.detector,
            "detect",
            return_value=SandboxDetectionResult(
                status=SandboxDetectionStatus.GIT_FAILED,
                errors=["Git command failed"],
                items=[],
                active_sandbox_count=0,
                warnings=[],
                fixes=[],
            ),
        ):
            result = pruner.prune()

        expected = (
            PruneResultBuilder().with_status(SandboxPruneStatus.GIT_FAILED).with_errors("Git command failed").build()
        )
        assert_model_equal(result, expected)

    def test_prune_returns_locked_on_workspace_lock_timeout(
        self,
        pruner_workspace: Path,
    ) -> None:
        """Workspace lock timeouts should return LOCKED status without crashing."""
        db = SandboxesRepository(pruner_workspace)
        pruner = SandboxPruner(pruner_workspace, db)

        with patch(
            "worktree.core.sandbox.services.pruner.WorkspaceLock.__enter__",
            side_effect=LockTimeoutError("Locked"),
        ):
            result = pruner.prune()

        expected = (
            PruneResultBuilder()
            .with_status(SandboxPruneStatus.LOCKED)
            .with_errors("Failed to acquire workspace lock: Locked")
            .build()
        )
        assert_model_equal(result, expected)

    def test_prune_returns_partial_success_on_item_failure(
        self,
        pruner_workspace: Path,
    ) -> None:
        """Errors during individual item pruning should produce PARTIAL_SUCCESS."""
        db = SandboxesRepository(pruner_workspace)
        branch_name = "worktree/sandbox-sbx_fail_branch"
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=pruner_workspace,
            check=True,
            capture_output=True,
        )

        pruner = SandboxPruner(pruner_workspace, db)

        with patch.object(
            GitRunner,
            "branch_delete",
            side_effect=RuntimeError("Permission denied"),
        ):
            result = pruner.prune()

        expected = (
            PruneResultBuilder()
            .with_status(SandboxPruneStatus.PARTIAL_SUCCESS)
            .with_item(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier=branch_name,
                action=PruneAction.FAILED,
                branch_name=branch_name,
                reason=f"Sandbox branch '{branch_name}' is not attached to any active sandbox or worktree",
                error=f"Failed to delete branch '{branch_name}': Permission denied",
            )
            .with_errors(f"Failed to delete branch '{branch_name}': Permission denied")
            .build()
        )
        assert_model_equal(result, expected)
