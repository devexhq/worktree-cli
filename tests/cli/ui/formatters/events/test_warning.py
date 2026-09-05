"""Tier 2 presentation contract tests for WarningFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import WarningEvent
from worktree.cli.ui.formatters.events.warning import WarningFormatter


class WarningFormatterTests:
    """Presentation contract tests for WarningFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = WarningFormatter()
        event = WarningEvent(message="Low disk space")
        assert formatter.to_json_serializable(event) == {"message": "Low disk space"}

    def test_to_rich_renders_message(self) -> None:
        formatter = WarningFormatter()
        event = WarningEvent(message="Low disk space")
        rendered = render_rich(formatter.to_rich(event))
        assert "Low disk space" in rendered
