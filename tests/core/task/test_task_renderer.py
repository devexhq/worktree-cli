"""Tests for pure task resolve/run error body formatters."""

from __future__ import annotations

from pathlib import Path

from getworktree.common.models import DefinitionResolutionResult, DefinitionResolutionStatus
from getworktree.core.db import RunStatus
from getworktree.core.runtime import RunOutcome
from getworktree.core.step import StepResult
from getworktree.core.task import format_task_resolve_failure, format_task_run_failure


class FormatTaskFailureTests:
    """Failure body formatters used by task error panels."""

    def test_format_task_resolve_failure_with_errors(self) -> None:
        result = DefinitionResolutionResult(
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name="missing",
            errors=["err-a", "err-b"],
        )
        assert format_task_resolve_failure(result) == "err-a\n\nerr-b"

    def test_format_task_resolve_failure_empty(self) -> None:
        result = DefinitionResolutionResult(
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name="missing",
            errors=[],
        )
        assert format_task_resolve_failure(result) == "Failed to resolve task."

    def test_format_task_run_failure_with_error_message(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.FAILED,
            error_message="top-level boom",
            sandbox_path=Path("/tmp/run"),
        )
        assert format_task_run_failure(outcome) == "top-level boom"

    def test_format_task_run_failure_step_errors(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.FAILED,
            step_results=[
                StepResult(
                    step_id="s1",
                    status="failed",
                    exit_code=1,
                    stdout="",
                    stderr="",
                    duration_seconds=0.1,
                    error_message="step one failed",
                ),
                StepResult(
                    step_id="s2",
                    status="failed",
                    exit_code=1,
                    stdout="",
                    stderr="",
                    duration_seconds=0.1,
                    error_message="step two failed",
                ),
            ],
            sandbox_path=Path("/tmp/run"),
        )
        assert format_task_run_failure(outcome) == "step one failed\nstep two failed"

    def test_format_task_run_failure_fallback(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.FAILED,
            sandbox_path=Path("/tmp/run"),
        )
        assert format_task_run_failure(outcome) == "Task execution failed."
