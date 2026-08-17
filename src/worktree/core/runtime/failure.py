"""Runtime failure orchestration helpers and prompter protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from worktree.core.step import FailurePolicy, FailureSpec, StepDefinition, StepResult

USER_CONTINUED_MARKER = "user continued after prompt_user"


class FailurePromptDecision(StrEnum):
    """User (or adapter) decision after a terminal ``prompt_user`` step failure."""

    RETRY = "retry"
    CONTINUE = "continue"
    ABORT = "abort"


class FailurePrompter(Protocol):
    """Injectable decision entrypoint for interactive step-failure handling."""

    def prompt_step_failure(
        self,
        *,
        step: StepDefinition,
        result: StepResult,
        diagnostic: str,
    ) -> FailurePromptDecision:
        """Return the caller's decision. Must not block for non-interactive callers."""
        ...


class RunPauseHook(Protocol):
    """Optional no-op extension point for a later durable pause product."""

    def on_pause(self, *, step: StepDefinition, result: StepResult) -> None:
        """Called immediately before an interactive failure prompt."""
        ...

    def on_resume(self, *, step: StepDefinition, decision: FailurePromptDecision) -> None:
        """Called immediately after an interactive failure prompt returns."""
        ...


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
