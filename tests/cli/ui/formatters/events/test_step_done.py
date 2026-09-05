"""Tier 2 presentation contract tests for StepDoneFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import StepDoneEvent
from worktree.cli.ui.formatters.events.step_done import StepDoneFormatter


class StepDoneFormatterTests:
    """Presentation contract tests for StepDoneFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = StepDoneFormatter()
        event = StepDoneEvent(
            idx=1,
            total=3,
            step_id="step-1",
            ok=True,
            exit_code=0,
            duration_seconds=1.5,
            error_message=None,
        )
        assert formatter.to_json_serializable(event) == {
            "idx": 1,
            "total": 3,
            "step_id": "step-1",
            "ok": True,
            "exit_code": 0,
            "duration_seconds": 1.5,
            "error_message": None,
        }

    def test_to_rich_when_completed_contains_step_id(self) -> None:
        formatter = StepDoneFormatter()
        event = StepDoneEvent(
            idx=1,
            total=3,
            step_id="step-1",
            ok=True,
            exit_code=0,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "step-1" in rendered
        assert "COMPLETED" in rendered

    def test_to_rich_failure_contains_error_message(self) -> None:
        formatter = StepDoneFormatter()
        event = StepDoneEvent(
            idx=1,
            total=3,
            step_id="step-1",
            ok=False,
            exit_code=1,
            error_message="Process crashed",
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "step-1" in rendered
        assert "FAILED" in rendered
        assert "Process crashed" in rendered
