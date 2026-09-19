"""Contract tests for runtime failure-orchestration helpers: policy resolution and diagnostics."""

from __future__ import annotations

from tests.harness.matchers import assert_model_equal
from worktree.common.models import FailurePolicy, OnFailureSpec
from worktree.core.runtime import USER_CONTINUED_MARKER, effective_terminal_policy
from worktree.core.runtime.failure import mark_continued_after_prompt, step_failure_diagnostic
from worktree.core.step import StepResult


class FailurePolicyHelperTests:
    """Contract tests for effective_terminal_policy, mark_continued_after_prompt, step_failure_diagnostic."""

    def test_effective_terminal_policy_retry_action_returns_on_max_retries_policy(self) -> None:
        spec = OnFailureSpec(action=FailurePolicy.RETRY, on_max_retries=FailurePolicy.CONTINUE)

        assert effective_terminal_policy(spec) == FailurePolicy.CONTINUE

    def test_effective_terminal_policy_non_retry_action_returns_action_unchanged(self) -> None:
        spec = OnFailureSpec(action=FailurePolicy.CONTINUE)

        assert effective_terminal_policy(spec) == FailurePolicy.CONTINUE

    def test_mark_continued_after_prompt_sets_status_ignored_and_appends_continued_marker(self) -> None:
        original = StepResult(
            step_id="publish",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.1,
            attempts=1,
            error_message="boom",
            errors=[],
            warnings=[],
            fixes=[],
        )

        updated = mark_continued_after_prompt(original)

        assert_model_equal(
            updated,
            StepResult(
                step_id="publish",
                status="ignored",
                exit_code=1,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                attempts=1,
                error_message=f"boom ({USER_CONTINUED_MARKER})",
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
        assert updated.ok is True

    def test_step_failure_diagnostic_prefers_error_message_over_stderr_and_exit_code(self) -> None:
        result = StepResult(
            step_id="publish",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="stderr output",
            duration_seconds=0.1,
            error_message="explicit failure",
        )

        assert step_failure_diagnostic(result) == "explicit failure"
