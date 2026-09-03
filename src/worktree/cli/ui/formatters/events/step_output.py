"""ComponentFormatter for StepOutputEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import StepOutputEvent
from worktree.common.types import ComponentFormatter


class StepOutputFormatter(ComponentFormatter[StepOutputEvent]):
    """Formatter for live step output lines."""

    def to_rich(self, data: StepOutputEvent) -> Text:
        """Render raw output text."""
        return Text(data.line)

    def to_json_serializable(self, data: StepOutputEvent) -> dict[str, Any]:
        """Convert StepOutputEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
