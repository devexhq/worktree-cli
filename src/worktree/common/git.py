"""Git CLI subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from worktree.common.constants import GIT_SUBPROCESS_TIMEOUT_SECONDS


def get_current_git_branch(path: Path) -> str:
    """Extract current active Git branch using standard Git CLI."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD (detached)"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"
