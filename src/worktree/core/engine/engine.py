"""Process handle: persist a run row and execute a Blueprint via run_steps."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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
from worktree.core.engine.exceptions import EngineResumeError, EngineRuntimeError
from worktree.core.engine.models import EngineResumeStatus
from worktree.core.runtime import (
    FailurePrompter,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunOutcome,
    parse_checkpoint,
    run_steps,
)
from worktree.core.step import LoopStepBlock, StepDefinition


class _DbPauseStore:
    """``RunPauseStore`` adapter backed by a task or workflow run repository."""

    def __init__(self, db: TasksDb | WorkflowsDb, session_id: str) -> None:
        self._db = db
        self._session_id = session_id

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Write checkpoint JSON and set the tracked run to paused."""
        self._db.save_pause(
            self._session_id,
            checkpoint.model_dump_json(),
            checkpoint.diagnostic,
        )

    def clear_pause(self) -> None:
        """Mark the tracked run running again after an in-process prompt returns."""
        self._db.update_status(self._session_id, RunStatus.RUNNING)

    def finalize(self, status: RunStatus, error_message: str | None) -> None:
        """Write the terminal (or paused) status after ``run_steps`` returns."""
        self._db.update_status(self._session_id, status, error_message=error_message)


@dataclass(frozen=True)
class _PreparedResume:
    """Validated resume inputs after classification succeeds."""

    checkpoint: RunCheckpoint
    steps: list[StepDefinition]
    db: TasksDb | WorkflowsDb


class Engine:
    """Process: sandbox, DB row, pause store, sequential step loop."""

    def __init__(self, cwd: Path | None = None) -> None:
        self.cwd = (cwd or Path.cwd()).resolve()
        self._tasks_db = TasksDb(self.cwd)
        self._workflows_db = WorkflowsDb(self.cwd)
        self.db: TasksDb | WorkflowsDb = self._tasks_db

    def run(
        self,
        blueprint: Blueprint,
        *,
        inputs: dict[str, str | int | bool] | None = None,
        use_sandbox: bool | None = None,
        keep: bool = False,
        agent: str | None = None,
        session_id: str | None = None,
        observer: RunObserver | None = None,
        failure_prompter: FailurePrompter | None = None,
        non_interactive: bool = False,
    ) -> RunOutcome:
        """Adapt ``blueprint`` into ``RunContext`` and delegate to ``run_steps``."""
        steps = self._sequential_steps(blueprint)
        sid = session_id or f"{blueprint.kind.value}_{uuid.uuid4().hex[:8]}"
        engine_warnings: list[str] = []
        pause_store = self._start_run(blueprint, sid, engine_warnings)
        caller_sandbox = True if use_sandbox is None else use_sandbox
        outcome = run_steps(
            RunContext(
                steps=steps,
                cwd=self.cwd,
                use_sandbox=caller_sandbox and blueprint.use_sandbox,
                keep=keep,
                agent=agent,
                observer=observer,
                inputs=inputs,
                non_interactive=non_interactive,
                failure_prompter=failure_prompter,
                pause_store=pause_store,
            )
        )
        if pause_store is not None:
            self._finish_run(pause_store, outcome, engine_warnings)
        return self._with_engine_warnings(outcome, engine_warnings)

    def resume(
        self,
        session_id: str,
        *,
        blueprint: Blueprint | None = None,
        observer: RunObserver | None = None,
        failure_prompter: FailurePrompter | None = None,
        non_interactive: bool = False,
    ) -> RunOutcome:
        """Classify a paused session, rebuild ``RunContext``, and re-enter ``run_steps``."""
        prepared = self._prepare_resume(session_id, blueprint)
        self.db = prepared.db
        pause_store = _DbPauseStore(prepared.db, session_id)
        engine_warnings: list[str] = []
        self._mark_running(pause_store, engine_warnings)
        outcome = run_steps(
            RunContext(
                steps=prepared.steps,
                cwd=self.cwd,
                use_sandbox=prepared.checkpoint.use_sandbox,
                keep=prepared.checkpoint.keep,
                agent=prepared.checkpoint.agent,
                observer=observer,
                inputs=prepared.checkpoint.inputs or None,
                non_interactive=non_interactive,
                failure_prompter=failure_prompter,
                pause_store=pause_store,
                resume_from=prepared.checkpoint,
            )
        )
        self._finish_run(pause_store, outcome, engine_warnings)
        return self._with_engine_warnings(outcome, engine_warnings)

    def _start_run(
        self,
        blueprint: Blueprint,
        session_id: str,
        warnings: list[str],
    ) -> _DbPauseStore | None:
        """Insert a RUNNING row and return a pause store, or warn and skip persistence."""
        self.db = self._db_for(blueprint.kind)
        try:
            self._insert_running(blueprint, session_id)
        except Exception as exc:
            warnings.append(f"Failed to record run start in database: {exc}")
            return None
        return _DbPauseStore(self.db, session_id)

    def _finish_run(
        self,
        pause_store: _DbPauseStore,
        outcome: RunOutcome,
        warnings: list[str],
    ) -> None:
        """Persist the outcome status when the start insert succeeded."""
        try:
            pause_store.finalize(outcome.status, outcome.error_message)
        except Exception as exc:
            warnings.append(f"Failed to update run status in database: {exc}")

    def _sequential_steps(self, blueprint: Blueprint, *, action: str = "run") -> list[StepDefinition]:
        """Return authored steps, or raise when any entry is a loop block."""
        steps: list[StepDefinition] = []
        for step in blueprint.steps:
            if isinstance(step, LoopStepBlock):
                raise EngineRuntimeError(f"Engine.{action} does not execute loop steps.")
            steps.append(step)
        return steps

    def _insert_running(self, blueprint: Blueprint, session_id: str) -> None:
        """Insert a RUNNING row for the bound repository."""
        if blueprint.kind is BlueprintKind.TASK:
            self.db.insert(session_id, task_name=blueprint.name, status=RunStatus.RUNNING)
            return
        self.db.insert(session_id, workflow_name=blueprint.name, branch_name="", status=RunStatus.RUNNING)

    def _db_for(self, kind: BlueprintKind) -> TasksDb | WorkflowsDb:
        """Return the run-tracking repository for ``kind``."""
        return self._tasks_db if kind is BlueprintKind.TASK else self._workflows_db

    def _with_engine_warnings(self, outcome: RunOutcome, engine_warnings: list[str]) -> RunOutcome:
        """Return ``outcome`` unchanged, or copy it with Engine warnings appended."""
        if not engine_warnings:
            return outcome
        return outcome.model_copy(update={"warnings": [*outcome.warnings, *engine_warnings]})

    def _mark_running(self, pause_store: _DbPauseStore, warnings: list[str]) -> None:
        """Set the paused row back to running, or record a persistence warning."""
        try:
            pause_store.clear_pause()
        except Exception as exc:
            warnings.append(f"Failed to update run status in database: {exc}")

    def _prepare_resume(self, session_id: str, blueprint: Blueprint | None) -> _PreparedResume:
        """Validate the paused row and return checkpoint, steps, and bound db."""
        row, db = self._lookup_resume_row(session_id, blueprint)
        self._require_paused(session_id, row.status)
        checkpoint = self._require_checkpoint(session_id, row.checkpoint_json)
        loaded = blueprint if blueprint is not None else self._load_resume_blueprint(session_id, row)
        steps = self._sequential_steps(loaded, action="resume")
        self._require_pending_step(session_id, checkpoint.pending_step_id, steps)
        return _PreparedResume(checkpoint=checkpoint, steps=steps, db=db)

    def _lookup_resume_row(
        self,
        session_id: str,
        blueprint: Blueprint | None,
    ) -> tuple[TaskRunRecord | WorkflowRunRecord, TasksDb | WorkflowsDb]:
        """Return the run row and repository for ``session_id``."""
        if blueprint is not None:
            db = self._db_for(blueprint.kind)
            row = db.get(session_id)
            if row is None:
                raise EngineResumeError(EngineResumeStatus.NOT_FOUND, f"Session '{session_id}' not found.")
            return row, db
        task_row = self._tasks_db.get(session_id)
        if task_row is not None:
            return task_row, self._tasks_db
        workflow_row = self._workflows_db.get(session_id)
        if workflow_row is not None:
            return workflow_row, self._workflows_db
        raise EngineResumeError(EngineResumeStatus.NOT_FOUND, f"Session '{session_id}' not found.")

    def _require_paused(self, session_id: str, status: RunStatus) -> None:
        """Raise when the stored row is not paused."""
        if status != RunStatus.PAUSED:
            raise EngineResumeError(
                EngineResumeStatus.WRONG_STATUS,
                f"Cannot resume session '{session_id}': status is '{status.value}' (expected paused).",
            )

    def _require_checkpoint(self, session_id: str, raw: str | None) -> RunCheckpoint:
        """Parse the stored checkpoint and reject a missing sandbox path."""
        checkpoint = parse_checkpoint(raw)
        if checkpoint is None:
            raise EngineResumeError(
                EngineResumeStatus.CORRUPT_CHECKPOINT,
                f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
            )
        if not checkpoint.use_sandbox:
            return checkpoint
        sandbox_path = checkpoint.sandbox_path or ""
        if sandbox_path and Path(sandbox_path).exists():
            return checkpoint
        raise EngineResumeError(
            EngineResumeStatus.MISSING_SANDBOX,
            f"Cannot resume session '{session_id}': sandbox path '{sandbox_path}' no longer exists.",
        )

    def _require_pending_step(
        self,
        session_id: str,
        pending_step_id: str,
        steps: list[StepDefinition],
    ) -> None:
        """Raise when the checkpoint points at a step that is not in the blueprint."""
        if pending_step_id not in {step.id for step in steps}:
            raise EngineResumeError(
                EngineResumeStatus.CORRUPT_CHECKPOINT,
                f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
            )

    def _load_resume_blueprint(
        self,
        session_id: str,
        row: TaskRunRecord | WorkflowRunRecord,
    ) -> Blueprint:
        """Load the catalog blueprint named by the paused row."""
        name = row.task_name if isinstance(row, TaskRunRecord) else row.workflow_name
        try:
            return Blueprint.load(name, catalog=Catalog(self.cwd))
        except (BlueprintNotFoundError, BlueprintLoadError, BlueprintValidationError) as exc:
            raise EngineResumeError(
                EngineResumeStatus.FAILED,
                f"Cannot resume session '{session_id}': blueprint '{name}' not found.",
            ) from exc
