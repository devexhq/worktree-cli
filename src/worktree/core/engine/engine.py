"""Process handle: persist a run row and execute a Blueprint via run_steps."""

from __future__ import annotations

import uuid
from pathlib import Path

from worktree.core.blueprint.services.blueprint import Blueprint
from worktree.core.catalog import Catalog
from worktree.core.db import BlueprintKind, RunsRepository, RunStatus
from worktree.core.engine.exceptions import EngineInputError, EngineRuntimeError
from worktree.core.engine.models import RunRequest
from worktree.core.engine.resumable import ResumableRun
from worktree.core.inputs import InputResolveResult
from worktree.core.runtime import (
    ExecutionIdentity,
    FailurePrompter,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunOutcome,
    run_steps,
)
from worktree.core.step import LoopStepBlock, StepDefinition


class _DbPauseStore:
    """``RunPauseStore`` adapter backed by RunsRepository."""

    def __init__(self, db: RunsRepository, session_id: str) -> None:
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

    def __init__(
        self,
        path: Path,
        db: RunsRepository | None = None,
        catalog: Catalog | None = None,
    ) -> None:
        self.path = path.resolve()
        self.cwd = self.path
        self.db = db if db is not None else RunsRepository(self.path)
        self.catalog = catalog if catalog is not None else Catalog(self.path)

    def run(self, blueprint: Blueprint, request: RunRequest | None = None) -> RunOutcome:
        """Adapt ``blueprint`` into ``RunContext`` and delegate to ``run_steps``."""
        req = request or RunRequest()
        steps = self._sequential_steps(blueprint)
        resolved = self._resolve_run_inputs(blueprint, req)
        sid = req.session_id or f"{blueprint.kind.value}_{uuid.uuid4().hex[:8]}"
        engine_warnings: list[str] = list(resolved.warnings)
        pause_store = self._start_run(blueprint, sid, engine_warnings)
        caller_sandbox = True if req.use_sandbox is None else req.use_sandbox
        identity = (
            ExecutionIdentity(task_name=blueprint.name, task_sha=sid)
            if blueprint.kind == BlueprintKind.TASK
            else ExecutionIdentity(workflow_name=blueprint.name, workflow_sha=sid)
        )

        outcome = run_steps(
            RunContext(
                steps=steps,
                cwd=self.path,
                use_sandbox=caller_sandbox and blueprint.use_sandbox,
                keep=req.keep,
                agent=req.agent,
                observer=req.observer,
                inputs=resolved.values,
                identity=identity,
                non_interactive=req.non_interactive,
                failure_prompter=req.failure_prompter,
                pause_store=pause_store,
            )
        )

        if pause_store is not None:
            self._finish_run(pause_store, outcome, engine_warnings)

        return self._finalize_outcome(outcome, sid, engine_warnings)

    def resume(
        self,
        session_id: str,
        *,
        blueprint: Blueprint | None = None,
        observer: RunObserver | None = None,
        failure_prompter: FailurePrompter | None = None,
        non_interactive: bool = False,
        catalog: Catalog | None = None,
    ) -> RunOutcome:
        """Classify a paused session, rebuild ``RunContext``, and re-enter ``run_steps``."""
        cat = catalog or self.catalog
        if cat is None:
            raise EngineRuntimeError("Engine.resume requires a Catalog instance.")

        loaded, db, checkpoint = ResumableRun.load(
            session_id,
            blueprint,
            path=self.path,
            db=self.db,
            catalog=cat,
        ).ready()
        steps = self._sequential_steps(loaded, action="resume")

        self.db = db
        pause_store = _DbPauseStore(db, session_id)
        engine_warnings: list[str] = []
        self._mark_running(pause_store, engine_warnings)
        identity = (
            checkpoint.identity
            if checkpoint.identity is not None
            else (
                ExecutionIdentity(task_name=loaded.name, task_sha=session_id)
                if loaded.kind == BlueprintKind.TASK
                else ExecutionIdentity(workflow_name=loaded.name, workflow_sha=session_id)
            )
        )

        outcome = run_steps(
            RunContext(
                steps=steps,
                cwd=self.path,
                use_sandbox=checkpoint.use_sandbox,
                keep=checkpoint.keep,
                agent=checkpoint.agent,
                observer=observer,
                inputs=checkpoint.inputs or None,
                identity=identity,
                non_interactive=non_interactive,
                failure_prompter=failure_prompter,
                pause_store=pause_store,
                resume_from=checkpoint,
            )
        )

        self._finish_run(pause_store, outcome, engine_warnings)

        return self._finalize_outcome(outcome, session_id, engine_warnings)

    def _start_run(
        self,
        blueprint: Blueprint,
        session_id: str,
        warnings: list[str],
    ) -> _DbPauseStore | None:
        """Insert a RUNNING row and return a pause store, or warn and skip persistence."""
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
            error_message = outcome.errors[0] if outcome.errors else None
            pause_store.finalize(outcome.status, error_message)
        except Exception as exc:
            warnings.append(f"Failed to update run status in database: {exc}")

    def _sequential_steps(self, blueprint: Blueprint, *, action: str = "run") -> list[StepDefinition | LoopStepBlock]:
        """Return authored steps from blueprint."""
        return list(blueprint.steps)

    def _insert_running(self, blueprint: Blueprint, session_id: str) -> None:
        """Insert a RUNNING row for the bound repository."""
        self.db.create(
            session_id=session_id,
            blueprint_name=blueprint.name,
            kind=blueprint.kind,
            branch_name="",
            status=RunStatus.RUNNING,
        )

    def _resolve_run_inputs(self, blueprint: Blueprint, request: RunRequest) -> InputResolveResult:
        """Apply defaults and required checks; raise before a run row is inserted."""
        result = blueprint.resolve_inputs(request.cli_args, overrides=request.inputs)
        if not result.ok:
            raise EngineInputError(result)
        return result

    def _finalize_outcome(self, outcome: RunOutcome, session_id: str, extra_warnings: list[str]) -> RunOutcome:
        """Stamp the session id and append Engine warnings onto ``outcome``."""
        update: dict[str, object] = {"session_id": session_id}
        if extra_warnings:
            update["warnings"] = [*outcome.warnings, *extra_warnings]
        return outcome.model_copy(update=update)

    def _mark_running(self, pause_store: _DbPauseStore, warnings: list[str]) -> None:
        """Set the paused row back to running, or record a persistence warning."""
        try:
            pause_store.clear_pause()
        except Exception as exc:
            warnings.append(f"Failed to update run status in database: {exc}")
