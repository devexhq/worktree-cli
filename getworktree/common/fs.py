"""File system paths for the worktree CLI."""

import json
import os
from pathlib import Path
from typing import Any

from getworktree.common.constants import GITIGNORE_ENTRY


def get_worktree_dir(cwd: Path) -> Path:
    """Return the worktree root path, relative to the CWD."""
    return cwd / ".worktree"


def get_worktree_config_file(cwd: Path) -> Path:
    """Return the worktree config file path, relative to CWD."""
    return get_worktree_dir(cwd) / "config.json"


def get_gitignore_file(cwd: Path) -> Path:
    """Return the .gitignore file path, relative to CWD."""
    return cwd / ".gitignore"


def get_session_dir(cwd: Path, session_id: str) -> Path:
    """Return the session artifact directory path, relative to CWD."""
    return get_worktree_dir(cwd) / "sessions" / session_id


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically with indent=2, UTF-8, and trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """Write text content atomically with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def is_git_repository(path: Path) -> bool:
    """Check whether the given directory contains a .git directory or file."""
    git_path = path / ".git"
    return git_path.exists()


def update_gitignore(gitignore_path: Path) -> bool:
    """Ensure /.worktree/ is excluded in .gitignore."""
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if "/.worktree/" in content or ".worktree" in content:
            return False

        prefix = "" if content.endswith("\n") else "\n"
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{GITIGNORE_ENTRY}")
        return True

    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write(GITIGNORE_ENTRY.lstrip())
    return True
