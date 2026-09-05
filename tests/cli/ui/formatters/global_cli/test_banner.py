"""Tier 2 presentation contract tests for WelcomeBannerFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import WelcomeBannerEvent
from worktree.cli.ui.formatters.global_cli.banner import WelcomeBannerFormatter


class WelcomeBannerFormatterTests:
    """Presentation contract tests for WelcomeBannerFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = WelcomeBannerFormatter()
        event = WelcomeBannerEvent(version="0.1.0")
        assert formatter.to_json_serializable(event) == {"version": "0.1.0"}

    def test_to_rich_renders_version(self) -> None:
        formatter = WelcomeBannerFormatter()
        event = WelcomeBannerEvent(version="1.2.3")
        rendered = render_rich(formatter.to_rich(event))
        assert "v1.2.3" in rendered
