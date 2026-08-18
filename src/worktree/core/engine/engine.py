"""Process handle: persist a run row and execute a Blueprint via run_steps."""

from __future__ import annotations

import uuid
from pathlib import Path

from worktree.core.blueprint import Blueprint, BlueprintKind
from worktree.core.db import RunStatus, TasksDb, WorkflowsDb
from worktree.core.engine.exceptions import EngineRuntimeError
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
        if not engine_warnings:
            return outcome
        return outcome.model_copy(update={"warnings": [*outcome.warnings, *engine_warnings]})

    def _start_run(
        self,
        blueprint: Blueprint,
        session_id: str,
        warnings: list[str],
    ) -> _DbPauseStore | None:
        """Insert a RUNNING row and return a pause store, or warn and skip persistence."""
        self.db = self._tasks_db if blueprint.kind is BlueprintKind.TASK else self._workflows_db
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

    def _sequential_steps(self, blueprint: Blueprint) -> list[StepDefinition]:
        """Return authored steps, or raise when any entry is a loop block."""
        steps: list[StepDefinition] = []
        for step in blueprint.steps:
            if isinstance(step, LoopStepBlock):
                raise EngineRuntimeError("Engine.run does not execute loop steps.")
            steps.append(step)
        return steps

    def _insert_running(self, blueprint: Blueprint, session_id: str) -> None:
        """Insert a RUNNING row for the bound repository."""
        if blueprint.kind is BlueprintKind.TASK:
            self.db.insert(session_id, task_name=blueprint.name, status=RunStatus.RUNNING)
            return
        self.db.insert(session_id, workflow_name=blueprint.name, branch_name="", status=RunStatus.RUNNING)
