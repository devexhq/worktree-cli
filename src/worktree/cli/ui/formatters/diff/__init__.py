"""Diff ComponentFormatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.diff.models import DiffResult

from .diff_result import DiffResultFormatter


def register_diff_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register diff formatters on the provided dispatcher."""
    dispatcher.register(DiffResult, DiffResultFormatter())


__all__ = [
    "DiffResultFormatter",
    "register_diff_formatters",
]
