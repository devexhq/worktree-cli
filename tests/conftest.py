from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import FileSystem, GitFileSystem


@pytest.fixture(autouse=True, scope="session")
def _set_test_terminal_width() -> None:
    """Set standard terminal width for test output assertions (e.g. Rich table formatting)."""
    os.environ["COLUMNS"] = "160"
    os.environ["PYTHONIOENCODING"] = "utf-8"


@pytest.fixture(scope="session")
def _git_repo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped template git repository to eliminate repeated subprocess calls."""
    template = tmp_path_factory.mktemp("git_repo_template")
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=template,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=template,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=template,
        check=True,
        capture_output=True,
        text=True,
    )
    (template / "f.txt").write_text("x\n", encoding="utf-8")
    (template / ".gitignore").write_text("/.worktree/\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "f.txt", ".gitignore"],
        cwd=template,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=template,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "feature"],
        cwd=template,
        check=True,
        capture_output=True,
    )
    return template


@pytest.fixture
def fs(tmp_path: Path) -> FileSystem:
    return FileSystem(tmp_path)


@pytest.fixture
def git_fs(tmp_path: Path, _git_repo_template: Path) -> GitFileSystem:
    target = tmp_path / "repo"
    shutil.copytree(_git_repo_template, target)
    return GitFileSystem(target)
