"""Global CLI formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.events import WelcomeBannerEvent
from worktree.cli.ui.formatters.common import DispatcherProtocol

from .banner import WelcomeBannerFormatter


def register_global_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register global CLI formatters on the provided dispatcher."""
    dispatcher.register(WelcomeBannerEvent, WelcomeBannerFormatter())


__all__ = [
    "WelcomeBannerFormatter",
    "register_global_formatters",
]
