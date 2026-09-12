"""Unit tests for runtime run outcome models."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import RunStatus
from worktree.core.runtime import RunCheckpoint, RunOutcome, parse_checkpoint
from worktree.core.step import StepResult


class RuntimeOutcomeModelTests:
    """Unit tests for RunOutcome properties and status classifications."""

    def test_run_outcome_ok_true_for_completed(self) -> None:
        outcome = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=Path("/tmp/run"))
        assert outcome.ok is True

    def test_run_outcome_ok_false_for_completed_with_errors(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.COMPLETED,
            errors=["unexpected post-run error"],
            sandbox_path=Path("/tmp/run"),
        )
        assert outcome.ok is False

    def test_run_outcome_ok_false_for_failed(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.FAILED,
            errors=["boom"],
            sandbox_path=Path("/tmp/run"),
        )
        assert outcome.ok is False

    def test_run_outcome_ok_false_for_cancelled(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.CANCELLED,
            errors=["Execution cancelled by user."],
            sandbox_path=Path("/tmp/run"),
        )
        assert outcome.ok is False

    def test_run_outcome_ok_false_for_paused(self) -> None:
        outcome = RunOutcome(
            status=RunStatus.PAUSED,
            errors=["Step 'publish' failed: exit code 1"],
            sandbox_path=Path("/tmp/run"),
        )
        assert outcome.ok is False


class RuntimeCheckpointModelTests:
    """Unit tests for RunCheckpoint serialization and parsing."""

    def test_checkpoint_json_round_trip(self) -> None:
        pending = StepResult(
            step_id="publish",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.1,
            error_message="exit code 1",
        )
        checkpoint = RunCheckpoint(
            next_step_index=2,
            step_results=[],
            sandbox_path="/abs/path/to/sandbox",
            use_sandbox=True,
            keep=False,
            inputs={"name": "demo"},
            pending_step_id="publish",
            diagnostic="Step 'publish' failed: exit code 1",
            pending_result=pending,
        )
        loaded = parse_checkpoint(checkpoint.model_dump_json())
        assert loaded == checkpoint

    def test_parse_checkpoint_rejects_missing_and_corrupt(self) -> None:
        assert parse_checkpoint(None) is None
        assert parse_checkpoint("") is None
        assert parse_checkpoint("{not-json") is None
