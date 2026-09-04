"""History ComponentFormatters decomposed into single-class modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.history.models import HistoryListResult, HistoryShowResult

from .history_list import HistoryListFormatter
from .history_show import HistoryShowFormatter


def register_history_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all history formatters on the provided dispatcher."""
    dispatcher.register(HistoryListResult, HistoryListFormatter())
    dispatcher.register(HistoryShowResult, HistoryShowFormatter())


__all__ = [
    "HistoryListFormatter",
    "HistoryShowFormatter",
    "register_history_formatters",
]
