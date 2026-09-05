"""Tier 2 presentation contract tests for LockWaitFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.events import LockWaitEvent
from worktree.cli.ui.formatters.events.lock_wait import LockWaitFormatter


class LockWaitFormatterTests:
    """Tier 2 presentation contract tests for LockWaitFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid="12345",
            timeout_seconds=30.0,
        )
        assert formatter.to_json_serializable(event) == {
            "lock_path": "/path/to/.worktree/.lock",
            "holder_pid": "12345",
            "timeout_seconds": 30.0,
        }

    def test_to_rich_with_holder_pid_contains_model_values(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid="12345",
            timeout_seconds=30.0,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "12345" in rendered
        assert ".lock" in rendered
        assert "30.0s" in rendered

    def test_to_rich_without_holder_pid_contains_model_values(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid=None,
            timeout_seconds=15.0,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "PID:" not in rendered
        assert ".lock" in rendered
        assert "15.0s" in rendered
