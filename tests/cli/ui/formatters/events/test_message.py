"""Tier 2 presentation contract tests for MessageFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import MessageEvent
from worktree.cli.ui.formatters.events.message import MessageFormatter


class MessageFormatterTests:
    """Presentation contract tests for MessageFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = MessageFormatter()
        event = MessageEvent(message="Operation finished", style="bold")
        assert formatter.to_json_serializable(event) == {
            "message": "Operation finished",
            "style": "bold",
        }

    def test_to_rich_renders_message_content(self) -> None:
        formatter = MessageFormatter()
        event = MessageEvent(message="Running task 'build'...")
        rendered = render_rich(formatter.to_rich(event))
        assert "Running task 'build'..." in rendered
