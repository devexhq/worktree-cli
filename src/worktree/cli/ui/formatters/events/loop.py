"""ComponentFormatter for LoopLifecycleEvent."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.events import LoopLifecycleEvent
from worktree.common.types import ComponentFormatter


def _build_conditions_evaluated_text(data: LoopLifecycleEvent) -> Group:
    """Build the per-condition Rich Text lines for a conditions_evaluated event.

    Content is appended to Text via .append rather than interpolated into a
    markup string, so loop ids and condition expressions never need escaping.
    """
    lines = [Text(f"[{data.loop_id}] Evaluated 'until' conditions:")]
    for condition in data.conditions:
        lines.append(Text(f"  - {condition.expression}: {condition.detail}"))
    if data.next_turn is not None:
        lines.append(Text(f"[{data.loop_id}] Conditions not met. Continuing to turn {data.next_turn}..."))
    return Group(*lines)


class LoopLifecycleFormatter(ComponentFormatter[LoopLifecycleEvent]):
    """Formatter for loop execution notices."""

    def to_rich(self, data: LoopLifecycleEvent) -> Text | Group:
        """Render loop progress, turn, evaluation, or termination line."""
        if data.action == "start":
            return Text(f"[{data.loop_id}] Starting loop block (max_iterations: {data.max_iterations})")
        if data.action == "turn_start":
            return Text(f"[{data.loop_id}] --- Iteration Turn {data.turn}/{data.max_iterations} ---")
        if data.action == "conditions_evaluated":
            return _build_conditions_evaluated_text(data)
        if data.action == "done":
            if data.status == "completed":
                return Text(f"[{data.loop_id}] Loop completed successfully in {data.turn} iteration(s).")
            return Text(f"[{data.loop_id}] Loop terminated with status '{data.status}' after {data.turn} iteration(s).")
        return Text(data.message or f"[{data.loop_id}] {data.action}")
