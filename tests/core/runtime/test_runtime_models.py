"""Unit tests for runtime run outcome models."""

from pathlib import Path

from worktree.core.db import RunStatus
from worktree.core.runtime import RunOutcome


def test_run_outcome_ok_true_for_completed() -> None:
    outcome = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=Path("/tmp/run"))
    assert outcome.ok is True


def test_run_outcome_ok_false_for_failed() -> None:
    outcome = RunOutcome(
        status=RunStatus.FAILED,
        error_message="boom",
        sandbox_path=Path("/tmp/run"),
    )
    assert outcome.ok is False


def test_run_outcome_ok_false_for_cancelled() -> None:
    outcome = RunOutcome(
        status=RunStatus.CANCELLED,
        error_message="Execution cancelled by user.",
        sandbox_path=Path("/tmp/run"),
    )
    assert outcome.ok is False
