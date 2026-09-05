"""Tier 2 presentation contract tests for LoopLifecycleFormatter."""

from __future__ import annotations

import pytest

from tests.helpers import render_rich
from worktree.cli.ui.events import LoopLifecycleEvent
from worktree.cli.ui.formatters.events.loop import LoopLifecycleFormatter


class LoopLifecycleFormatterTests:
    """Presentation contract tests for LoopLifecycleFormatter."""

    @pytest.mark.parametrize(
        ("action", "turn", "max_iterations", "status", "expected_tokens"),
        [
            pytest.param("start", 0, 5, None, ("loop_1", "5"), id="start"),
            pytest.param("turn_start", 2, 5, None, ("loop_1", "2", "5"), id="turn_start"),
            pytest.param("done", 3, 5, "completed", ("loop_1", "3", "completed"), id="done_completed"),
        ],
    )
    def test_to_rich_renders_expected_action_text(
        self,
        action: str,
        turn: int,
        max_iterations: int,
        status: str | None,
        expected_tokens: tuple[str, ...],
    ) -> None:
        formatter = LoopLifecycleFormatter()
        event = LoopLifecycleEvent(
            loop_id="loop_1",
            action=action,
            turn=turn,
            max_iterations=max_iterations,
            status=status,
        )
        rendered = render_rich(formatter.to_rich(event))
        for token in expected_tokens:
            assert token in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = LoopLifecycleFormatter()
        event = LoopLifecycleEvent(
            loop_id="loop_1",
            action="start",
            turn=1,
            max_iterations=5,
            status=None,
            message="Starting",
        )
        assert formatter.to_json_serializable(event) == {
            "loop_id": "loop_1",
            "action": "start",
            "turn": 1,
            "max_iterations": 5,
            "status": None,
            "message": "Starting",
        }
