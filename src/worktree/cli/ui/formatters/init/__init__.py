"""Init ComponentFormatters."""

from __future__ import annotations

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.bootstrap import WorkspaceInitResult

from .init_view import WorkspaceInitView
from .workspace_init import InitOutcomeFormatter, WorkspaceInitFormatter


def register_init_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all init formatters on the provided dispatcher."""
    dispatcher.register(WorkspaceInitResult, WorkspaceInitFormatter())


__all__ = [
    "InitOutcomeFormatter",
    "WorkspaceInitFormatter",
    "WorkspaceInitView",
    "register_init_formatters",
]
