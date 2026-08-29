"""Unit tests for stateless GitRunner and Git exceptions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from worktree.core.git import (
    GitCommandError,
    GitError,
    GitNotFoundError,
    GitPlumbingTimeoutError,
    GitRunner,
)


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with a commit on main."""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path), check=True, capture_output=True)
    (path / "file.txt").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(path), check=True, capture_output=True)


def test_git_runner_run_success(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    output = GitRunner.run(["rev-parse", "--abbrev-ref", "HEAD"], path=tmp_path)
    assert output == "main"


def test_git_runner_run_not_found(tmp_path: Path) -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError("No git")):
        with pytest.raises(GitNotFoundError) as exc_info:
            GitRunner.run(["status"], path=tmp_path)
        assert "git not found" in str(exc_info.value)
        assert isinstance(exc_info.value, GitError)


def test_git_runner_run_timeout(tmp_path: Path) -> None:
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git", "status"], timeout=1)):
        with pytest.raises(GitPlumbingTimeoutError) as exc_info:
            GitRunner.run(["status"], path=tmp_path, timeout=1)
        assert "timed out after 1s" in str(exc_info.value)


def test_git_runner_run_command_error(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    with pytest.raises(GitCommandError) as exc_info:
        GitRunner.run(["checkout", "nonexistent-branch-xyz"], path=tmp_path)
    assert exc_info.value.returncode != 0
    assert "nonexistent-branch-xyz" in exc_info.value.stderr or "Git execution failed" in str(exc_info.value)


def test_git_runner_get_current_branch(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    assert GitRunner.get_current_branch(repo_dir) == "main"

    # Non-git directory returns unknown
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    assert GitRunner.get_current_branch(non_git) == "unknown"


def test_git_runner_status_porcelain(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    assert GitRunner.status_porcelain(tmp_path) == []

    (tmp_path / "new_file.txt").write_text("hello", encoding="utf-8")
    status = GitRunner.status_porcelain(tmp_path)
    assert len(status) == 1
    assert "new_file.txt" in status[0]


def test_git_runner_worktree_lifecycle(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    target = tmp_path / "wt1"
    GitRunner.worktree_add(tmp_path, target_path=target, branch="test-branch", base_ref="main")
    assert target.exists()
    assert (target / "file.txt").read_text(encoding="utf-8") == "initial\n"

    GitRunner.worktree_remove(tmp_path, target_path=target, force=True)
    assert not target.exists()

    GitRunner.worktree_prune(tmp_path)
    GitRunner.branch_delete(tmp_path, branch="test-branch", force=True)


def test_git_runner_diff_and_apply(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    base_commit = GitRunner.rev_parse(tmp_path, rev="HEAD")

    # Make modifications
    (tmp_path / "file.txt").write_text("modified\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new content\n", encoding="utf-8")
    GitRunner.add_intent_to_add(tmp_path, target=".")

    diff_text = GitRunner.diff(tmp_path, base_commit=base_commit)
    assert "modified" in diff_text
    assert "untracked.txt" in diff_text

    touched = GitRunner.diff_name_only(tmp_path, base_commit=base_commit)
    assert "file.txt" in touched
    assert "untracked.txt" in touched

    stat = GitRunner.diff_stat(tmp_path, base_commit=base_commit)
    assert "file.txt" in stat

    # Check apply_check and apply in a fresh clone / repo
    dest = tmp_path / "dest"
    dest.mkdir()
    _init_git_repo(dest)

    ret, _, _ = GitRunner.apply_check(dest, diff_text)
    assert ret == 0

    ret, _, _ = GitRunner.apply(dest, diff_text)
    assert ret == 0
    assert (dest / "file.txt").read_text(encoding="utf-8") == "modified\n"
    assert (dest / "untracked.txt").read_text(encoding="utf-8") == "new content\n"

    GitRunner.add_all(dest)
    GitRunner.commit(dest, "squash commit")
    assert GitRunner.rev_parse(dest, rev="HEAD") != base_commit
