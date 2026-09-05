"""Tier 2 presentation contract tests for SandboxLifecycleFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import SandboxLifecycleEvent
from worktree.cli.ui.formatters.events.sandbox import SandboxLifecycleFormatter


class SandboxLifecycleFormatterTests:
    """Presentation contract tests for SandboxLifecycleFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxLifecycleFormatter()
        event = SandboxLifecycleEvent(
            action="ready",
            path="/tmp/sbx",
            active=True,
            kept=None,
        )
        assert formatter.to_json_serializable(event) == {
            "action": "ready",
            "path": "/tmp/sbx",
            "active": True,
            "kept": None,
        }

    def test_to_rich_renders_action_and_path(self) -> None:
        formatter = SandboxLifecycleFormatter()
        event = SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True)
        rendered = render_rich(formatter.to_rich(event))
        assert "/tmp/sbx" in rendered
        assert "Active" in rendered
