"""Unit tests for SandboxDetector and stale sandbox classification."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch

from tests.helpers import GitFileSystem
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.git.exceptions import GitCommandError
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox import (
    GitSandboxManager,
    SandboxDetectionStatus,
    SandboxDetector,
    StaleSandboxCategory,
    detect_stale_sandboxes,
)


def test_detect_clean_repository(git_fs: GitFileSystem) -> None:
    """Clean repo with no sandboxes should return 0 stale items."""
    git_fs.init_repo()
    db = WorktreeDb(path=git_fs.base_path)
    detector = SandboxDetector(git_fs.base_path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert result.status == SandboxDetectionStatus.OK
    assert result.total_stale_count == 0
    assert not result.has_stale_items
    assert not result.has_dirty_orphans
    assert result.active_sandbox_count == 0


def test_detect_stale_worktree_refs(git_fs: GitFileSystem) -> None:
    """Stale git worktree refs pointing to deleted directories should be detected."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    target = path / ".worktree" / "sandboxes" / "sbx_wt1"
    GitRunner.worktree_add(path, target_path=target, branch="worktree/sandbox-sbx_wt1", base_ref="main")

    # Manually delete the directory without git worktree remove
    shutil.rmtree(target)

    detector = SandboxDetector(path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert result.has_stale_items
    assert len(result.stale_worktrees) == 1
    assert result.stale_worktrees[0].category == StaleSandboxCategory.STALE_WORKTREE_REF
    assert result.stale_worktrees[0].path == target
    assert result.stale_worktrees[0].branch_name == "worktree/sandbox-sbx_wt1"


def test_detect_orphaned_directories(git_fs: GitFileSystem) -> None:
    """Orphaned sandbox directories on disk without active DB records should be detected."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    sandboxes_dir = path / ".worktree" / "sandboxes"
    sandboxes_dir.mkdir(parents=True, exist_ok=True)

    # 1. Untracked clean directory
    dir_clean = sandboxes_dir / "sbx_clean"
    dir_clean.mkdir()

    # 2. Untracked dirty directory with git worktree and uncommitted changes
    dir_dirty = sandboxes_dir / "sbx_dirty"
    GitRunner.worktree_add(path, target_path=dir_dirty, branch="worktree/sandbox-sbx_dirty", base_ref="main")
    (dir_dirty / "uncommitted.txt").write_text("wip", encoding="utf-8")

    # 3. Cleaned record directory
    dir_cleaned = sandboxes_dir / "sbx_cleaned"
    dir_cleaned.mkdir()
    db.sandboxes.create(
        id="sbx_cleaned",
        branch_name="worktree/sandbox-sbx_cleaned",
        base_commit="abc",
        sandbox_path=dir_cleaned,
    )
    db.sandboxes.update_status("sbx_cleaned", SandboxStatus.CLEANED)

    detector = SandboxDetector(path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert result.has_stale_items
    assert result.has_dirty_orphans
    assert len(result.orphaned_directories) == 3

    dirty_item = next(i for i in result.orphaned_directories if i.identifier == "sbx_dirty")
    assert dirty_item.is_dirty
    assert dirty_item.dirty_file_count >= 1

    clean_item = next(i for i in result.orphaned_directories if i.identifier == "sbx_clean")
    assert not clean_item.is_dirty

    cleaned_item = next(i for i in result.orphaned_directories if i.identifier == "sbx_cleaned")
    assert "cleaned" in cleaned_item.reason


def test_detect_stale_db_records(git_fs: GitFileSystem) -> None:
    """Active DB records with missing paths on disk should be detected."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    missing_path = path / ".worktree" / "sandboxes" / "sbx_missing"
    db.sandboxes.create(
        id="sbx_missing",
        branch_name="worktree/sandbox-sbx_missing",
        base_commit="abc",
        sandbox_path=missing_path,
    )

    detector = SandboxDetector(path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert len(result.stale_db_records) == 1
    record_item = result.stale_db_records[0]
    assert record_item.category == StaleSandboxCategory.STALE_DB_RECORD
    assert record_item.session_id == "sbx_missing"
    assert record_item.identifier == "sbx_missing"


def test_detect_stale_branches(git_fs: GitFileSystem) -> None:
    """Unlinked temporary sandbox branches should be detected."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    subprocess.run(
        ["git", "branch", "worktree/sandbox-sbx_abandoned"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )

    detector = SandboxDetector(path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert len(result.stale_branches) == 1
    branch_item = result.stale_branches[0]
    assert branch_item.category == StaleSandboxCategory.STALE_BRANCH
    assert branch_item.branch_name == "worktree/sandbox-sbx_abandoned"


def test_active_sandboxes_are_protected(git_fs: GitFileSystem) -> None:
    """Valid active sandboxes must not be categorized as stale."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    manager = GitSandboxManager(path, db.sandboxes)

    create_res = manager.create_sandbox(session_id="sbx_active_123")
    assert create_res.ok
    assert create_res.session is not None

    detector = SandboxDetector(path, db.sandboxes)
    result = detector.detect()

    assert result.ok
    assert result.total_stale_count == 0
    assert result.active_sandbox_count == 1


def test_detect_helper_and_manager_facade(git_fs: GitFileSystem) -> None:
    """Verify helper function and GitSandboxManager facade methods."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    manager = GitSandboxManager(path, db.sandboxes)

    # Calling via detect_stale_sandboxes helper
    res1 = detect_stale_sandboxes(path, db.sandboxes)
    assert res1.ok

    # Calling via manager facade
    res2 = manager.detect_stale_sandboxes()
    assert res2.ok
    assert res2.total_stale_count == res1.total_stale_count


def test_detect_git_error_handling(git_fs: GitFileSystem) -> None:
    """Git failures should be classified as GIT_FAILED without crashing."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    detector = SandboxDetector(path, db.sandboxes)

    with patch.object(
        GitRunner, "worktree_list", side_effect=GitCommandError(["git", "worktree", "list"], 1, "", "fatal error")
    ):
        result = detector.detect()
        assert not result.ok
        assert result.status == SandboxDetectionStatus.GIT_FAILED
        assert len(result.errors) == 1
        assert "GIT_FAILED" in result.errors[0]


def test_detect_db_error_handling(git_fs: GitFileSystem) -> None:
    """Database failures should return ERROR status without crashing."""
    git_fs.init_repo()
    path = git_fs.base_path
    db = WorktreeDb(path=path)
    detector = SandboxDetector(path, db.sandboxes)

    with patch.object(db.sandboxes, "list", side_effect=RuntimeError("database locked")):
        result = detector.detect()
        assert not result.ok
        assert result.status == SandboxDetectionStatus.ERROR
        assert len(result.errors) == 1
        assert "database locked" in result.errors[0]
