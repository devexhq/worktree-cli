"""ComponentFormatter for StepStartEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import StepStartEvent
from worktree.common.types import ComponentFormatter


class StepStartFormatter(ComponentFormatter[StepStartEvent]):
    """Formatter for step start notices."""

    def to_rich(self, data: StepStartEvent) -> Text:
        """Render step start progress line."""
        step_label = data.name or data.step_id
        cmd_info = f" (command: {data.command})" if data.command else ""
        return Text.from_markup(f"[STEP {data.idx}/{data.total}] Executing {step_label}{cmd_info}...")

    def to_json_serializable(self, data: StepStartEvent) -> dict[str, Any]:
        """Convert StepStartEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
