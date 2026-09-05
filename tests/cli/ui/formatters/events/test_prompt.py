"""Tier 2 presentation contract tests for PromptFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import PromptEvent, PromptOption
from worktree.cli.ui.formatters.events.prompt import PromptFormatter


class PromptFormatterTests:
    """Presentation contract tests for PromptFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = PromptFormatter()
        option = PromptOption(key="c", label="Continue", decision="continue")
        event = PromptEvent(
            prompt_type="step_failure",
            prompt_id="step-1",
            kind="task",
            title="Action Needed",
            diagnostic="Step timed out",
            options=[option],
            default="c",
        )
        assert formatter.to_json_serializable(event) == {
            "prompt_type": "step_failure",
            "prompt_id": "step-1",
            "kind": "task",
            "title": "Action Needed",
            "diagnostic": "Step timed out",
            "options": [
                {
                    "key": "c",
                    "label": "Continue",
                    "decision": "continue",
                }
            ],
            "default": "c",
        }

    def test_to_rich_renders_prompt_options(self) -> None:
        formatter = PromptFormatter()
        option = PromptOption(key="c", label="Continue", decision="continue")
        event = PromptEvent(
            prompt_type="step_failure",
            prompt_id="step-1",
            kind="task",
            title="Action Needed",
            diagnostic="Step timed out",
            options=[option],
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "Action Needed" in rendered
        assert "Continue" in rendered
        assert "c" in rendered
