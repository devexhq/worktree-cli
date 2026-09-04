"""ComponentFormatter for RunSuccessEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import RunSuccessEvent
from worktree.common.types import ComponentFormatter


class RunSuccessFormatter(ComponentFormatter[RunSuccessEvent]):
    """Formatter for blueprint run completion summaries."""

    def to_rich(self, data: RunSuccessEvent) -> Text:
        """Render green success summary line."""
        kind_str = data.kind.value.capitalize()
        return Text.from_markup(
            f"[bold green]{kind_str} Run Completed:[/] {data.blueprint_name} "
            f"(session: {data.session_id}, status: {data.status.value})"
        )

    def to_json_serializable(self, data: RunSuccessEvent) -> dict[str, Any]:
        """Convert RunSuccessEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
