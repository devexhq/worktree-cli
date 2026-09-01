"""Unit tests for SandboxPruner and safe prune execution service."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch

from tests.helpers import GitFileSystem
from worktree.common.lock import LockTimeoutError
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox import (
    GitSandboxManager,
    PruneAction,
    SandboxDetectionResult,
    SandboxDetectionStatus,
    SandboxPruner,
    SandboxPruneResult,
    SandboxPruneStatus,
    StaleSandboxCategory,
    prune_stale_sandboxes,
)


def test_prune_clean_repository(git_fs: GitFileSystem) -> None:
    """Pruning a clean repository should return OK with 0 items."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune()

    assert result.ok
    assert result.status == SandboxPruneStatus.OK
    assert result.pruned_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 0
    assert not result.dry_run


def test_prune_dry_run_simulation(git_fs: GitFileSystem) -> None:
    """Dry-run should accurately report planned actions without modifying disk, git, or DB."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clean orphan dir
    clean_dir = sandboxes_dir / "sbx_clean"
    clean_dir.mkdir()

    # 2. Dirty orphan dir
    dirty_dir = sandboxes_dir / "sbx_dirty"
    GitRunner.worktree_add(path, target_path=dirty_dir, branch="worktree/sandbox-sbx_dirty", base_ref="main")
    (dirty_dir / "dirty.txt").write_text("wip", encoding="utf-8")

    # 3. Stale DB record
    missing_path = sandboxes_dir / "sbx_missing"
    db.sandboxes.create(
        id="sbx_missing",
        branch_name="worktree/sandbox-sbx_missing",
        base_commit="abc",
        sandbox_path=missing_path,
    )

    # 4. Stale branch
    subprocess.run(
        ["git", "branch", "worktree/sandbox-sbx_dead"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune(dry_run=True, force=False)

    assert result.ok
    assert result.dry_run is True
    assert result.pruned_count == 3  # clean dir, stale db record, stale branch
    assert result.skipped_count == 1  # dirty dir skipped

    # Verify no mutations occurred
    assert clean_dir.exists()
    assert dirty_dir.exists()
    record = db.sandboxes.get("sbx_missing")
    assert record is not None and record.status == SandboxStatus.ACTIVE
    branches = GitRunner.list_branches(path, pattern="worktree/sandbox-*")
    assert "worktree/sandbox-sbx_dead" in branches


def test_prune_dirty_orphan_skipped_by_default(git_fs: GitFileSystem) -> None:
    """Dirty orphan directory must be preserved with SKIPPED status when force=False."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    dirty_dir = sandboxes_dir / "sbx_dirty_orphan"
    GitRunner.worktree_add(path, target_path=dirty_dir, branch="worktree/sandbox-sbx_dirty_orphan", base_ref="main")
    (dirty_dir / "wip.txt").write_text("changes", encoding="utf-8")

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune(force=False)

    assert result.ok
    assert result.skipped_count == 1
    assert result.pruned_count == 0
    assert dirty_dir.exists()
    skipped_item = result.skipped_items[0]
    assert skipped_item.action == PruneAction.SKIPPED
    assert "uncommitted changes" in skipped_item.reason


def test_prune_dirty_orphan_deleted_with_force(git_fs: GitFileSystem) -> None:
    """Dirty orphan directory must be removed when force=True."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    dirty_dir = sandboxes_dir / "sbx_dirty_forced"
    GitRunner.worktree_add(path, target_path=dirty_dir, branch="worktree/sandbox-sbx_dirty_forced", base_ref="main")
    (dirty_dir / "wip.txt").write_text("changes", encoding="utf-8")

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune(force=True)

    assert result.ok
    assert result.pruned_count == 1
    assert result.skipped_count == 0
    assert not dirty_dir.exists()


def test_prune_clean_orphan_directory(git_fs: GitFileSystem) -> None:
    """Clean orphan directory must be deleted even with force=False."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    clean_dir = sandboxes_dir / "sbx_clean_orphan"
    clean_dir.mkdir()

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune(force=False)

    assert result.ok
    assert result.pruned_count == 1
    assert not clean_dir.exists()


def test_prune_stale_worktree_refs(git_fs: GitFileSystem) -> None:
    """Stale worktree administrative entries should be pruned."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    target = path / ".worktree" / "sandboxes" / "sbx_stale_wt"
    GitRunner.worktree_add(path, target_path=target, branch="worktree/sandbox-sbx_stale_wt", base_ref="main")

    # Delete directory directly without git worktree remove
    shutil.rmtree(target)

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune()

    assert result.ok
    assert any(item.category == StaleSandboxCategory.STALE_WORKTREE_REF for item in result.pruned_items)


def test_prune_stale_db_records(git_fs: GitFileSystem) -> None:
    """Active DB records with missing paths must be updated to CLEANED."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    missing_path = path / ".worktree" / "sandboxes" / "sbx_db_stale"
    db.sandboxes.create(
        id="sbx_db_stale",
        branch_name="worktree/sandbox-sbx_db_stale",
        base_commit="abc",
        sandbox_path=missing_path,
    )

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune()

    assert result.ok
    assert result.pruned_count == 1
    record = db.sandboxes.get("sbx_db_stale")
    assert record is not None
    assert record.status == SandboxStatus.CLEANED


def test_prune_stale_branches(git_fs: GitFileSystem) -> None:
    """Stale sandbox temporary branches must be deleted."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    branch_name = "worktree/sandbox-sbx_stale_branch"
    subprocess.run(
        ["git", "branch", branch_name],
        cwd=str(path),
        check=True,
        capture_output=True,
    )

    pruner = SandboxPruner(path, db.sandboxes)
    result = pruner.prune()

    assert result.ok
    assert result.pruned_count == 1
    branches = GitRunner.list_branches(path, pattern="worktree/sandbox-*")
    assert branch_name not in branches


def test_prune_combined_and_idempotency(git_fs: GitFileSystem) -> None:
    """Pruning all stale categories, followed by a second run, must be clean and idempotent."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clean orphan dir with DB record
    dir1 = sandboxes_dir / "sbx_c1"
    dir1.mkdir()
    db.sandboxes.create(
        id="sbx_c1",
        branch_name="worktree/sandbox-sbx_c1",
        base_commit="abc",
        sandbox_path=dir1,
    )
    db.sandboxes.update_status("sbx_c1", SandboxStatus.CLEANED)

    # 2. Stale branch
    subprocess.run(
        ["git", "branch", "worktree/sandbox-sbx_c2"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )

    # 3. Active valid sandbox (must NOT be pruned)
    manager = GitSandboxManager(path, db.sandboxes)
    create_res = manager.create_sandbox(session_id="sbx_protected")
    assert create_res.ok

    # First prune run
    result1 = manager.prune_sandboxes()
    assert result1.ok
    assert result1.pruned_count == 2
    assert not dir1.exists()
    assert (sandboxes_dir / "sbx_protected").exists()

    # Second prune run (idempotent no-op)
    result2 = manager.prune_sandboxes()
    assert result2.ok
    assert result2.pruned_count == 0
    assert result2.total_stale_count == 0 if hasattr(result2, "total_stale_count") else len(result2.items) == 0


def test_prune_manager_facade_and_helper(git_fs: GitFileSystem) -> None:
    """Verify prune_stale_sandboxes helper and GitSandboxManager facade method."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    manager = GitSandboxManager(path, db.sandboxes)

    res_helper = prune_stale_sandboxes(path, db.sandboxes, dry_run=True)
    assert isinstance(res_helper, SandboxPruneResult)
    assert res_helper.ok

    res_manager = manager.prune_sandboxes(dry_run=True)
    assert isinstance(res_manager, SandboxPruneResult)
    assert res_manager.ok


def test_prune_detection_git_failure(git_fs: GitFileSystem) -> None:
    """When detector returns GIT_FAILED, prune should abort with GIT_FAILED status."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    pruner = SandboxPruner(path, db.sandboxes)

    with patch.object(
        pruner.detector,
        "detect",
        return_value=SandboxDetectionResult(
            status=SandboxDetectionStatus.GIT_FAILED,
            errors=["Git command failed"],
        ),
    ):
        result = pruner.prune()
        assert not result.ok
        assert result.status == SandboxPruneStatus.GIT_FAILED
        assert "Git command failed" in result.errors[0]


def test_prune_lock_timeout_handling(git_fs: GitFileSystem) -> None:
    """Workspace lock timeouts should return LOCKED status without crashing."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    pruner = SandboxPruner(path, db.sandboxes)

    with patch("worktree.core.sandbox.services.pruner.WorkspaceLock.__enter__", side_effect=LockTimeoutError("Locked")):
        result = pruner.prune()
        assert not result.ok
        assert result.status == SandboxPruneStatus.LOCKED
        assert len(result.errors) == 1
        assert "Failed to acquire workspace lock" in result.errors[0]


def test_prune_partial_failure_handling(git_fs: GitFileSystem) -> None:
    """Errors during individual item pruning should produce PARTIAL_SUCCESS."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    branch_name = "worktree/sandbox-sbx_fail_branch"
    subprocess.run(
        ["git", "branch", branch_name],
        cwd=str(path),
        check=True,
        capture_output=True,
    )

    pruner = SandboxPruner(path, db.sandboxes)
    with patch.object(GitRunner, "branch_delete", side_effect=RuntimeError("Permission denied")):
        result = pruner.prune()
        assert not result.ok
        assert result.status == SandboxPruneStatus.PARTIAL_SUCCESS
        assert result.failed_count == 1
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0]
