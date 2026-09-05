"""Tier 2 presentation contract tests for StepStartFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import StepStartEvent
from worktree.cli.ui.formatters.events.step_start import StepStartFormatter


class StepStartFormatterTests:
    """Presentation contract tests for StepStartFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = StepStartFormatter()
        event = StepStartEvent(
            idx=1,
            total=3,
            step_id="step-1",
            name="Run Tests",
            command="pytest",
        )
        assert formatter.to_json_serializable(event) == {
            "idx": 1,
            "total": 3,
            "step_id": "step-1",
            "name": "Run Tests",
            "command": "pytest",
        }

    def test_to_rich_renders_step_and_command(self) -> None:
        formatter = StepStartFormatter()
        event = StepStartEvent(
            idx=1,
            total=3,
            step_id="step-1",
            name="Run Tests",
            command="pytest",
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "Run Tests" in rendered
        assert "pytest" in rendered
