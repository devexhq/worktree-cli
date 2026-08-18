"""Process handle: persist a run row and execute a Blueprint via run_steps."""

from __future__ import annotations

import uuid
from pathlib import Path

from worktree.core.blueprint import Blueprint, BlueprintKind
from worktree.core.db import RunStatus, TasksDb, WorkflowsDb
from worktree.core.engine.exceptions import EngineResumeError, EngineRuntimeError
from worktree.core.engine.resumable import ResumableRun
from worktree.core.runtime import (
    FailurePrompter,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunOutcome,
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
        loaded, db, checkpoint = self._require_resumable(session_id, blueprint)
        steps = self._sequential_steps(loaded, action="resume")
        self.db = db
        pause_store = _DbPauseStore(db, session_id)
        engine_warnings: list[str] = []
        self._mark_running(pause_store, engine_warnings)
        outcome = run_steps(
            RunContext(
                steps=steps,
                cwd=self.cwd,
                use_sandbox=checkpoint.use_sandbox,
                keep=checkpoint.keep,
                agent=checkpoint.agent,
                observer=observer,
                inputs=checkpoint.inputs or None,
                non_interactive=non_interactive,
                failure_prompter=failure_prompter,
                pause_store=pause_store,
                resume_from=checkpoint,
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

    def _require_resumable(
        self,
        session_id: str,
        blueprint: Blueprint | None,
    ) -> tuple[Blueprint, TasksDb | WorkflowsDb, RunCheckpoint]:
        """Load a paused session or raise the classified resume error."""
        resumable_run = ResumableRun.load(session_id, blueprint, cwd=self.cwd)
        if not resumable_run.is_resumable:
            raise EngineResumeError(resumable_run.status, str(resumable_run))
        assert resumable_run.blueprint is not None
        assert resumable_run.db is not None
        assert resumable_run.checkpoint is not None
        return resumable_run.blueprint, resumable_run.db, resumable_run.checkpoint

    def _mark_running(self, pause_store: _DbPauseStore, warnings: list[str]) -> None:
        """Set the paused row back to running, or record a persistence warning."""
        try:
            pause_store.clear_pause()
        except Exception as exc:
            warnings.append(f"Failed to update run status in database: {exc}")
