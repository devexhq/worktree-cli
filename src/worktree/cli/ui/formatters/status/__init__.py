"""Status ComponentFormatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.status.models import WorktreeStatusResult

from .worktree_status import WorktreeStatusFormatter


def register_status_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register status formatters on the provided dispatcher."""
    dispatcher.register(WorktreeStatusResult, WorktreeStatusFormatter())


__all__ = [
    "WorktreeStatusFormatter",
    "register_status_formatters",
]
