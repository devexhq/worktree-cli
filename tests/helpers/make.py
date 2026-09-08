from __future__ import annotations

from typing import Any

from worktree.core.db import RunStatus
from worktree.core.runtime import RunCheckpoint
from worktree.core.runtime.models import RunOutcome
from worktree.core.step import StepResult


def make_run_outcome(**kwargs: Any) -> RunOutcome:
    defaults = {
        "status": RunStatus.COMPLETED,
        "step_results": [make_step_result()],
        "errors": [],
        "warnings": [],
        "sandbox_kept": False,
        "sandbox_path": ".worktree/sandboxes/sbx-run-1",
        "session_id": "run-1",
    }
    fields = {**defaults, **kwargs}
    return RunOutcome.model_validate(fields)


def make_step_result(**kwargs: Any) -> StepResult:
    defaults = {
        "errors": [],
        "warnings": [],
        "fixes": [],
        "step_id": "step_one",
        "status": "completed",
        "exit_code": 0,
        "stdout": "step-completed-ok\n",
        "stderr": "",
        "duration_seconds": 0.05,
        "attempts": 1,
        "error_message": None,
    }
    fields = {**defaults, **kwargs}
    return StepResult.model_validate(fields)


def make_ok_result(*, step_id: str = "step-1", **overrides: Any) -> StepResult:
    """Convenience helper for a successful completed StepResult."""
    return make_step_result(step_id=step_id, status="completed", exit_code=0, stdout="ok", stderr="", **overrides)


def make_failed_result(*, step_id: str = "step-1", **overrides: Any) -> StepResult:
    """Convenience helper for a failed StepResult."""
    defaults: dict[str, Any] = {
        "status": "failed",
        "exit_code": 1,
        "stdout": "",
        "stderr": "boom",
    }
    defaults.update(overrides)
    return make_step_result(step_id=step_id, **defaults)


def make_checkpoint(*, step_id: str = "step-1", **overrides: Any) -> RunCheckpoint:
    """Generate a valid RunCheckpoint instance with test defaults."""
    defaults: dict[str, Any] = {
        "version": 1,
        "next_step_index": 1,
        "step_results": [make_ok_result(step_id=step_id)],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": False,
        "pending_step_id": "step-2",
        "diagnostic": "",
        "pending_result": None,
    }
    defaults.update(overrides)
    return RunCheckpoint.model_validate(defaults)
