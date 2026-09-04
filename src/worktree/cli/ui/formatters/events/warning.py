"""ComponentFormatter for WarningEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import WarningEvent
from worktree.common.types import ComponentFormatter


class WarningFormatter(ComponentFormatter[WarningEvent]):
    """Formatter for warning notices."""

    def to_rich(self, data: WarningEvent) -> Text:
        """Render warning notice in yellow."""
        return Text.from_markup(f"[yellow]Warning:[/] {data.message}")

    def to_json_serializable(self, data: WarningEvent) -> dict[str, Any]:
        """Convert WarningEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
