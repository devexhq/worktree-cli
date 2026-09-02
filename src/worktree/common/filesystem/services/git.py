from __future__ import annotations

from pathlib import Path

from worktree.common.constants import GITIGNORE_ENTRY


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
