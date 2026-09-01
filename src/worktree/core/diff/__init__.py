"""Core diff domain package."""

from worktree.core.diff.facade import Diff
from worktree.core.diff.models import DiffResult, DiffStatus

__all__ = [
    "Diff",
    "DiffResult",
    "DiffStatus",
]
