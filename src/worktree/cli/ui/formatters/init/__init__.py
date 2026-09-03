"""Init ComponentFormatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.bootstrap import WorkspaceInitResult

from .workspace_init import InitOutcomeFormatter, WorkspaceInitFormatter


def register_init_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all init formatters on the provided dispatcher."""
    dispatcher.register(WorkspaceInitResult, WorkspaceInitFormatter())


__all__ = [
    "InitOutcomeFormatter",
    "WorkspaceInitFormatter",
    "register_init_formatters",
]
