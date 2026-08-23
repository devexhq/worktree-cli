"""Unit tests for runtime failure helpers."""

from __future__ import annotations

from worktree.core.runtime import (
    USER_CONTINUED_MARKER,
    effective_terminal_policy,
)
from worktree.core.runtime.failure import mark_continued_after_prompt, step_failure_diagnostic
from worktree.core.step import FailurePolicy, FailureSpec, StepResult


class RuntimeFailurePolicyTests:
    """Unit tests for runtime failure diagnostics, continuation markers, and terminal policies."""

    def test_effective_terminal_policy_retry_uses_on_max_retries(self) -> None:
        spec = FailureSpec(action=FailurePolicy.RETRY, on_max_retries=FailurePolicy.PROMPT_USER)
        assert effective_terminal_policy(spec) == FailurePolicy.PROMPT_USER

    def test_effective_terminal_policy_non_retry_returns_action(self) -> None:
        spec = FailureSpec(action=FailurePolicy.ABORT)
        assert effective_terminal_policy(spec) == FailurePolicy.ABORT

    def test_mark_continued_after_prompt_sets_ignored_and_marker(self) -> None:
        result = StepResult(
            step_id="s1",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.1,
            error_message="boom",
        )
        continued = mark_continued_after_prompt(result)
        assert continued.status == "ignored"
        assert continued.ok is True
        assert USER_CONTINUED_MARKER in (continued.error_message or "")
        assert "boom" in (continued.error_message or "")

    def test_step_failure_diagnostic_prefers_error_message(self) -> None:
        result = StepResult(
            step_id="s1",
            status="failed",
            exit_code=7,
            stdout="",
            stderr="err",
            duration_seconds=0.1,
            error_message="msg",
        )
        assert step_failure_diagnostic(result) == "msg"
