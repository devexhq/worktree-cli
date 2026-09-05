"""Status ComponentFormatters."""

from __future__ import annotations

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.status.models import WorktreeStatusResult

from .status_view import StatusHealth, StatusView
from .worktree_status import WorktreeStatusFormatter


def register_status_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register status formatters on the provided dispatcher."""
    dispatcher.register(WorktreeStatusResult, WorktreeStatusFormatter())


__all__ = [
    "StatusHealth",
    "StatusView",
    "WorktreeStatusFormatter",
    "register_status_formatters",
]
