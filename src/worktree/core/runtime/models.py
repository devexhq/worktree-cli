"""Shared run-context models for step execution engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from worktree.core.db import RunStatus
from worktree.core.git_sandbox import SandboxSession
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


class RunCheckpoint(BaseModel):
    """JSON-serializable pause payload sufficient to resume a run."""

    model_config = {"extra": "forbid", "strict": True}

    version: int = 1
    next_step_index: int
    step_results: list[StepResult] = Field(default_factory=list)
    sandbox_path: str | None = None
    sandbox_id: str | None = None
    sandbox_name: str | None = None
    sandbox_branch: str | None = None
    sandbox_base_commit: str | None = None
    use_sandbox: bool = True
    keep: bool = False
    agent: str | None = None
    inputs: dict[str, str | int | bool] = Field(default_factory=dict)
    pending_step_id: str
    diagnostic: str
    pending_result: StepResult | None = None


class RunPauseStore(Protocol):
    """Domain adapter that persists and clears durable pause checkpoints."""

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Write checkpoint JSON and set the tracked run to paused."""
        ...

    def clear_pause(self) -> None:
        """Mark the tracked run running again after an in-process prompt returns."""
        ...


def parse_checkpoint(raw: str | None) -> RunCheckpoint | None:
    """Load a checkpoint from JSON, or return None when missing or corrupt."""
    if raw is None or not raw.strip():
        return None
    try:
        return RunCheckpoint.model_validate_json(raw)
    except (ValueError, TypeError):
        return None


@dataclass
class StepLoopState:
    """Mutable per-run bookkeeping threaded through the step loop."""

    target_dir: Path
    session: SandboxSession | None
    step_results: list[StepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
    pause_store: RunPauseStore | None = None
    resume_from: RunCheckpoint | None = None


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
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sandbox_kept: bool = False
    sandbox_path: Path
    session_id: str | None = None

    @property
    def ok(self) -> bool:
        """Return True when the run completed successfully."""
        return self.status == RunStatus.COMPLETED and not self.errors
