"""Core diff domain package."""

from worktree.core.diff.facade import Diff
from worktree.core.diff.models import DiffResult, DiffStatus
from worktree.core.diff.renderers import render_diff
from worktree.core.diff.services import DiffService
from worktree.core.diff.writer import get_session_dir, write_session_diff

__all__ = [
    "Diff",
    "DiffResult",
    "DiffService",
    "DiffStatus",
    "get_session_dir",
    "render_diff",
    "write_session_diff",
]
