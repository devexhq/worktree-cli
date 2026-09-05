"""Tier 2 presentation contract tests for RunSuccessFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import RunSuccessEvent
from worktree.cli.ui.formatters.events.run_success import RunSuccessFormatter
from worktree.core.db import BlueprintKind, RunStatus


class RunSuccessFormatterTests:
    """Presentation contract tests for RunSuccessFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = RunSuccessFormatter()
        event = RunSuccessEvent(
            session_id="sess_123",
            blueprint_name="my_task",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        assert formatter.to_json_serializable(event) == {
            "session_id": "sess_123",
            "blueprint_name": "my_task",
            "kind": "task",
            "status": "completed",
        }

    def test_to_rich_renders_model_values(self) -> None:
        formatter = RunSuccessFormatter()
        event = RunSuccessEvent(
            session_id="sess_123",
            blueprint_name="my_task",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "my_task" in rendered
        assert "sess_123" in rendered
        assert "completed" in rendered
