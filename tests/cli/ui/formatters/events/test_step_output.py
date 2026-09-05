"""Tier 2 presentation contract tests for StepOutputFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import StepOutputEvent
from worktree.cli.ui.formatters.events.step_output import StepOutputFormatter


class StepOutputFormatterTests:
    """Presentation contract tests for StepOutputFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = StepOutputFormatter()
        event = StepOutputEvent(step_id="step-1", line="building...", stream="stdout")
        assert formatter.to_json_serializable(event) == {
            "step_id": "step-1",
            "line": "building...",
            "stream": "stdout",
        }

    def test_to_rich_renders_line(self) -> None:
        formatter = StepOutputFormatter()
        event = StepOutputEvent(step_id="step-1", line="building...")
        rendered = render_rich(formatter.to_rich(event))
        assert "building..." in rendered
