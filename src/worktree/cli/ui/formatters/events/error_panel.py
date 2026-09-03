"""ComponentFormatter for ErrorPanelEvent."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel

from worktree.cli.ui.events import ErrorPanelEvent
from worktree.common.types import ComponentFormatter


class ErrorPanelFormatter(ComponentFormatter[ErrorPanelEvent]):
    """Formatter for error panels."""

    def to_rich(self, data: ErrorPanelEvent) -> Panel:
        """Render error panel with border and title."""
        return Panel(data.message, title=data.title, border_style=data.border_style)

    def to_json_serializable(self, data: ErrorPanelEvent) -> dict[str, Any]:
        """Convert ErrorPanelEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
