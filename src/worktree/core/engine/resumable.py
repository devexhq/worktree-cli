"""Paused-session handle: classify a row and expose whether it can resume."""

from __future__ import annotations

from pathlib import Path

from worktree.core.blueprint import (
    Blueprint,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintValidationError,
)
from worktree.core.catalog import Catalog
from worktree.core.db import RunStatus, TaskRunRecord, TasksDb, WorkflowRunRecord, WorkflowsDb
from worktree.core.engine.models import EngineResumeStatus
from worktree.core.runtime import RunCheckpoint, parse_checkpoint
from worktree.core.step import StepDefinition


class ResumableRun:
    """Inspect a stored session. ``load`` never raises; ``is_resumable`` reports readiness."""

    def __init__(
        self,
        session_id: str,
        *,
        cwd: Path,
        status: EngineResumeStatus,
        message: str = "",
        checkpoint: RunCheckpoint | None = None,
        steps: list[StepDefinition] | None = None,
        db: TasksDb | WorkflowsDb | None = None,
        blueprint: Blueprint | None = None,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.status = status
        self.message = message
        self.checkpoint = checkpoint
        self.steps = steps or []
        self.db = db
        self.blueprint = blueprint

    def __str__(self) -> str:
        """Return the classification message for EngineResumeError."""
        return self.message

    @property
    def is_resumable(self) -> bool:
        """Return True when the session is paused and the checkpoint matches the blueprint."""
        return (
            self.status is EngineResumeStatus.OK
            and self.db is not None
            and self.checkpoint is not None
            and self.blueprint is not None
        )

    @classmethod
    def load(
        cls,
        session_id: str,
        blueprint: Blueprint | None = None,
        *,
        cwd: Path | None = None,
    ) -> ResumableRun:
        """Classify a session without raising. Check ``is_resumable`` before resuming."""
        root = (cwd or Path.cwd()).resolve()
        return cls._classify(session_id, blueprint, root)

    @classmethod
    def _classify(cls, session_id: str, blueprint: Blueprint | None, cwd: Path) -> ResumableRun:
        """Walk row, status, checkpoint, and blueprint checks in order."""
        found = cls._lookup_row(session_id, blueprint, cwd)
        if found is None:
            return cls._rejected(session_id, cwd, EngineResumeStatus.NOT_FOUND, f"Session '{session_id}' not found.")

        row, db = found
        if row.status != RunStatus.PAUSED:
            return cls._rejected(
                session_id,
                cwd,
                EngineResumeStatus.WRONG_STATUS,
                f"Cannot resume session '{session_id}': status is '{row.status.value}' (expected paused).",
            )

        checkpoint = cls._parse_checkpoint(session_id, row.checkpoint_json, cwd)
        if isinstance(checkpoint, ResumableRun):
            return checkpoint

        loaded = blueprint if blueprint is not None else cls._load_blueprint(session_id, row, cwd)
        if isinstance(loaded, ResumableRun):
            return loaded

        steps = [step for step in loaded.steps if isinstance(step, StepDefinition)]
        if checkpoint.pending_step_id not in {step.id for step in steps}:
            return cls._rejected(
                session_id,
                cwd,
                EngineResumeStatus.CORRUPT_CHECKPOINT,
                f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
            )

        return cls(
            session_id,
            cwd=cwd,
            status=EngineResumeStatus.OK,
            checkpoint=checkpoint,
            steps=steps,
            db=db,
            blueprint=loaded,
        )

    @classmethod
    def _rejected(
        cls,
        session_id: str,
        cwd: Path,
        status: EngineResumeStatus,
        message: str,
    ) -> ResumableRun:
        """Build a non-resumable handle for a classification failure."""
        return cls(session_id, cwd=cwd, status=status, message=message)

    @classmethod
    def _lookup_row(
        cls,
        session_id: str,
        blueprint: Blueprint | None,
        cwd: Path,
    ) -> tuple[TaskRunRecord | WorkflowRunRecord, TasksDb | WorkflowsDb] | None:
        """Return the run row and repository, or None when the session is missing."""
        if blueprint is not None:
            db: TasksDb | WorkflowsDb = TasksDb(cwd) if blueprint.kind is BlueprintKind.TASK else WorkflowsDb(cwd)
            row = db.get(session_id)
            return (row, db) if row is not None else None

        task_db = TasksDb(cwd)
        task_row = task_db.get(session_id)
        if task_row is not None:
            return task_row, task_db

        workflow_db = WorkflowsDb(cwd)
        workflow_row = workflow_db.get(session_id)
        if workflow_row is not None:
            return workflow_row, workflow_db

        return None

    @classmethod
    def _parse_checkpoint(cls, session_id: str, raw: str | None, cwd: Path) -> RunCheckpoint | ResumableRun:
        """Return a parsed checkpoint, or a rejected handle when it cannot be used."""
        checkpoint = parse_checkpoint(raw)
        if checkpoint is None:
            return cls._rejected(
                session_id,
                cwd,
                EngineResumeStatus.CORRUPT_CHECKPOINT,
                f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
            )

        if not checkpoint.use_sandbox:
            return checkpoint

        sandbox_path = checkpoint.sandbox_path or ""
        if sandbox_path and Path(sandbox_path).exists():
            return checkpoint

        return cls._rejected(
            session_id,
            cwd,
            EngineResumeStatus.MISSING_SANDBOX,
            f"Cannot resume session '{session_id}': sandbox path '{sandbox_path}' no longer exists.",
        )

    @classmethod
    def _load_blueprint(
        cls,
        session_id: str,
        row: TaskRunRecord | WorkflowRunRecord,
        cwd: Path,
    ) -> Blueprint | ResumableRun:
        """Load the catalog blueprint named by the paused row."""
        name = row.task_name if isinstance(row, TaskRunRecord) else row.workflow_name

        try:
            return Blueprint.load(name, catalog=Catalog(cwd))
        except (BlueprintNotFoundError, BlueprintLoadError, BlueprintValidationError):
            return cls._rejected(
                session_id,
                cwd,
                EngineResumeStatus.FAILED,
                f"Cannot resume session '{session_id}': blueprint '{name}' not found.",
            )
