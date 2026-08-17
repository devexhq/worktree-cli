"""Runtime failure orchestration helpers."""

from __future__ import annotations

from worktree.core.step import FailurePolicy, FailureSpec, StepResult

USER_CONTINUED_MARKER = "user continued after prompt_user"


def effective_terminal_policy(spec: FailureSpec) -> FailurePolicy:
    """Resolve the terminal escalation after step-local recovery finishes.

    When ``action == retry``, step execution already exhausted its local budget;
    the terminal policy is ``on_max_retries``. Otherwise the action itself is
    terminal (never ``retry``).
    """
    if spec.action == FailurePolicy.RETRY:
        return spec.on_max_retries
    return spec.action


def step_failure_diagnostic(result: StepResult) -> str:
    """Build a compact diagnostic string for a failed step result."""
    return result.error_message or result.stderr or f"exit code {result.exit_code}"


def mark_continued_after_prompt(result: StepResult) -> StepResult:
    """Rewrite a failed step as non-fatal after the user chooses continue."""
    diagnostic = step_failure_diagnostic(result)
    marker = f"{diagnostic} ({USER_CONTINUED_MARKER})" if diagnostic else USER_CONTINUED_MARKER
    return result.model_copy(update={"status": "ignored", "error_message": marker})
