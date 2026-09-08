from __future__ import annotations

from typing import Any

from sqlmodel import SQLModel

from worktree.core.db import (
    BaseRepository,
    BlueprintKind,
    RunRecord,
    RunsRepository,
    RunStatus,
)
from worktree.core.runtime import RunCheckpoint
from worktree.core.runtime.models import RunOutcome
from worktree.core.step import StepResult


class BaseFactory[ModelT: SQLModel, RepoT: BaseRepository]:
    """Base factory supporting static pure builds and repo-bound persistence."""

    _model: type[ModelT]

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Override in subclasses to provide test defaults."""
        return {}

    @classmethod
    def build(cls, **kwargs: Any) -> ModelT:
        """Pure, stateless factory to generate an in-memory model with defaults."""
        fields = {**cls.defaults(), **kwargs}
        return cls._model.model_validate(fields)

    @classmethod
    def create(cls, repo: RepoT, **kwargs: Any) -> ModelT:
        """Persist a factory instance using the bound repository session."""
        instance = cls.build(**kwargs)
        with repo.session() as session:
            session.add(instance)
            session.commit()
            session.refresh(instance)
        return instance


class RunFactory(BaseFactory[RunRecord, RunsRepository]):
    _model = RunRecord

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {
            "session_id": "run-1",
            "blueprint_name": "task-1",
            "kind": BlueprintKind.TASK,
            "status": RunStatus.COMPLETED,
            "branch_name": "main",
            "pid": None,
            "started_at": "2026-08-19 01:00:00",
            "completed_at": "2026-08-19 01:00:15",
            "error_message": None,
            "checkpoint_json": None,
        }


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
