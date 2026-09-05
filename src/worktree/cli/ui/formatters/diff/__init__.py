"""Diff ComponentFormatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.diff.models import DiffResult

from .diff_result import DiffResultFormatter

if TYPE_CHECKING:
    from rich.console import Console


def register_diff_formatters(dispatcher: DispatcherProtocol, console: Console | None = None) -> None:
    """Register diff formatters on the provided dispatcher."""
    effective_console = console or getattr(dispatcher, "_custom_console", None)
    dispatcher.register(DiffResult, DiffResultFormatter(console=effective_console))


__all__ = [
    "DiffResultFormatter",
    "register_diff_formatters",
]
