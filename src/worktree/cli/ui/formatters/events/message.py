"""ComponentFormatter for MessageEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import MessageEvent
from worktree.common.types import ComponentFormatter


class MessageFormatter(ComponentFormatter[MessageEvent]):
    """Formatter for generic message lines."""

    def to_rich(self, data: MessageEvent) -> Text:
        """Render formatted or styled message text."""
        if data.style is not None:
            return Text(data.message, style=data.style)
        return Text.from_markup(data.message)

    def to_json_serializable(self, data: MessageEvent) -> dict[str, Any]:
        """Convert MessageEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
