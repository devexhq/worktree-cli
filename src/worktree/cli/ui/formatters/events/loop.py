"""ComponentFormatter for LoopLifecycleEvent."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.events import LoopLifecycleEvent
from worktree.common.types import ComponentFormatter


class LoopLifecycleFormatter(ComponentFormatter[LoopLifecycleEvent]):
    """Formatter for loop execution notices."""

    def to_rich(self, data: LoopLifecycleEvent) -> Text:
        """Render loop progress, turn, evaluation, or termination line."""
        if data.action == "start":
            return Text(f"[{data.loop_id}] Starting loop block (max_iterations: {data.max_iterations})")
        if data.action == "turn_start":
            return Text(f"[{data.loop_id}] --- Iteration Turn {data.turn}/{data.max_iterations} ---")
        if data.action == "conditions_evaluated":
            return Text(data.message or f"[{data.loop_id}] Evaluated 'until' conditions")
        if data.action == "done":
            if data.status == "completed":
                return Text(f"[{data.loop_id}] Loop completed successfully in {data.turn} iteration(s).")
            return Text(f"[{data.loop_id}] Loop terminated with status '{data.status}' after {data.turn} iteration(s).")
        return Text(data.message or f"[{data.loop_id}] {data.action}")

    def to_json_serializable(self, data: LoopLifecycleEvent) -> dict[str, Any]:
        """Convert LoopLifecycleEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
