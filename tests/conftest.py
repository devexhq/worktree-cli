"""Global pytest fixtures and test execution harness configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from worktree.common.constants import REQUIRED_SUBDIRS


@pytest.fixture
def isolated_workspace(tmp_path: Path) -> Path:
    """Create a clean filesystem root with standard .worktree/ structure.

    Args:
        tmp_path: Ephemeral pytest directory fixture.

    Returns:
        Path to the isolated workspace root containing .worktree/.
    """
    workspace = tmp_path / "workspace"
    dot_worktree = workspace / ".worktree"
    dot_worktree.mkdir(parents=True, exist_ok=True)

    for subdir in REQUIRED_SUBDIRS:
        (dot_worktree / subdir).mkdir(parents=True, exist_ok=True)

    (dot_worktree / "sandboxes").mkdir(parents=True, exist_ok=True)
    (dot_worktree / "catalog").mkdir(parents=True, exist_ok=True)

    return workspace


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Initialize a bare-minimum Git repository with user identity and root commit on main.

    Args:
        tmp_path: Ephemeral pytest directory fixture.

    Returns:
        Path to the initialized Git repository root.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    readme_path = repo / "README.md"
    readme_path.write_text("# Test Repo\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    return repo


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a preconfigured Typer CliRunner with width 160 and NO_COLOR=1.

    Returns:
        CliRunner instance configured with NO_COLOR=1 and COLUMNS=160.
    """
    return CliRunner(env={"NO_COLOR": "1", "COLUMNS": "160"})
