"""Fluent RunOutcome result builder for Worktree CLI test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from worktree.core.db import RunStatus
from worktree.core.runtime import RunOutcome
from worktree.core.step.models import StepResult


class RunOutcomeBuilder:
    """Fluent builder for constructing expected RunOutcome models in tests."""

    def __init__(self, sandbox_path: Path | None = None) -> None:
        self._status: RunStatus = RunStatus.COMPLETED
        self._step_results: list[StepResult] = []
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._sandbox_kept: bool = False
        self._sandbox_path: Path | None = sandbox_path
        self._session_id: str | None = None

    def with_status(self, status: RunStatus) -> Self:
        """Set the classified run outcome status."""
        self._status = status
        return self

    def with_step_results(self, *step_results: StepResult) -> Self:
        """Append expected per-step results, in execution order."""
        self._step_results.extend(step_results)
        return self

    def with_errors(self, *errors: str) -> Self:
        """Append expected error messages."""
        self._errors.extend(errors)
        return self

    def with_warnings(self, *warnings: str) -> Self:
        """Append expected warning messages."""
        self._warnings.extend(warnings)
        return self

    def with_sandbox_kept(self, kept: bool = True) -> Self:
        """Set whether the sandbox worktree was preserved after the run."""
        self._sandbox_kept = kept
        return self

    def with_sandbox_path(self, sandbox_path: Path | None = None) -> Self:
        """Override the execution directory or sandbox worktree path."""
        self._sandbox_path = sandbox_path
        return self

    def with_session_id(self, session_id: str | None) -> Self:
        """Set the associated session identifier."""
        self._session_id = session_id
        return self

    def build(self) -> RunOutcome:
        """Assemble and return the complete RunOutcome."""
        return RunOutcome.model_construct(
            status=self._status,
            step_results=list(self._step_results),
            errors=list(self._errors),
            warnings=list(self._warnings),
            sandbox_kept=self._sandbox_kept,
            sandbox_path=self._sandbox_path,
            session_id=self._session_id,
        )
