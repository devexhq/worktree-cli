"""Shared run-context models for step execution engines."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from worktree.core.db import RunStatus
from worktree.core.step import StepDefinition, StepResult


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


@dataclass(frozen=True)
class RunContext:
    """Immutable inputs for a multi-step run."""

    steps: list[StepDefinition]
    cwd: Path
    use_sandbox: bool = True
    keep: bool = False
    agent: str | None = None
    observer: RunObserver | None = None
    inputs: dict[str, str | int | bool] | None = None
    non_interactive: bool = False
    failure_prompter: FailurePrompter | None = None
    pause_hook: RunPauseHook | None = None


class RunObserver(Protocol):
    """Optional progress hooks for sandbox and step lifecycle events."""

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        """Called after the execution directory is chosen."""
        ...

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Called immediately before a step begins."""
        ...

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Called immediately after a step finishes."""
        ...

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Called after sandbox cleanup/keep decision is applied."""
        ...


class RunOutcome(BaseModel):
    """Structured result of ``run_steps``."""

    model_config = {"extra": "forbid", "strict": True}

    status: RunStatus
    step_results: list[StepResult] = Field(default_factory=list)
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sandbox_kept: bool = False
    sandbox_path: Path

    @property
    def ok(self) -> bool:
        """Return True when the run completed successfully."""
        return self.status == RunStatus.COMPLETED
