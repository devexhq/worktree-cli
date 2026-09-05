"""Tier 2 presentation contract tests for ErrorPanelFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import ErrorPanelEvent
from worktree.cli.ui.formatters.events.error_panel import ErrorPanelFormatter


class ErrorPanelFormatterTests:
    """Presentation contract tests for ErrorPanelFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = ErrorPanelFormatter()
        event = ErrorPanelEvent(title="Error", message="Boom", border_style="red")
        assert formatter.to_json_serializable(event) == {
            "title": "Error",
            "message": "Boom",
            "border_style": "red",
        }

    def test_to_rich_renders_title_and_message(self) -> None:
        formatter = ErrorPanelFormatter()
        event = ErrorPanelEvent(title="Custom Error", message="Something broke")
        rendered = render_rich(formatter.to_rich(event))
        assert "Custom Error" in rendered
        assert "Something broke" in rendered
