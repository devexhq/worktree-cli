"""Resume a paused workflow session through the shared runtime engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worktree.core.catalog.services.inventory import get_catalog_item
from worktree.core.db import (
    BlueprintKind,
    CatalogItemType,
    RunRecord,
    RunsDb,
    RunStatus,
)
from worktree.core.runtime import (
    FailurePrompter,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunOutcome,
    parse_checkpoint,
    run_steps,
)
from worktree.core.step import StepDefinition
from worktree.core.workflows.models import (
    WorkflowDefinition,
    WorkflowResumeResult,
    WorkflowResumeStatus,
)
from worktree.core.workflows.services.pause import WorkflowPauseStore


def _standard_steps(definition: WorkflowDefinition) -> list[StepDefinition]:
    return [step for step in (definition.steps or []) if isinstance(step, StepDefinition)]


def _resume_error(status: WorkflowResumeStatus, message: str) -> WorkflowResumeResult:
    return WorkflowResumeResult(status=status, errors=[message])


def _validate_resume_row(session_id: str, row: RunRecord | None) -> WorkflowResumeResult | None:
    if row is None or row.kind != BlueprintKind.WORKFLOW:
        return _resume_error(
            WorkflowResumeStatus.NOT_FOUND,
            f"Workflow session '{session_id}' not found.",
        )
    if row.status != RunStatus.PAUSED:
        return _resume_error(
            WorkflowResumeStatus.WRONG_STATUS,
            f"Cannot resume session '{session_id}': status is '{row.status.value}' (expected paused).",
        )
    return None


def _validate_checkpoint(session_id: str, raw: str | None) -> tuple[RunCheckpoint | None, WorkflowResumeResult | None]:
    checkpoint = parse_checkpoint(raw)
    if checkpoint is None:
        return None, _resume_error(
            WorkflowResumeStatus.CORRUPT_CHECKPOINT,
            f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
        )
    if checkpoint.use_sandbox:
        sandbox_path = checkpoint.sandbox_path or ""
        if not sandbox_path or not Path(sandbox_path).exists():
            return None, _resume_error(
                WorkflowResumeStatus.MISSING_SANDBOX,
                f"Cannot resume session '{session_id}': sandbox path '{sandbox_path}' no longer exists.",
            )
    return checkpoint, None


def _load_resume_steps(
    session_id: str,
    row: RunRecord,
    checkpoint: RunCheckpoint,
    cwd: Path,
) -> tuple[list[StepDefinition] | None, WorkflowResumeResult | None]:
    loaded = get_catalog_item(
        row.blueprint_name,
        CatalogItemType.WORKFLOW,
        definition_cls=WorkflowDefinition,
        cwd=cwd,
    )
    if not loaded.ok or not isinstance(loaded.definition, WorkflowDefinition):
        return None, _resume_error(
            WorkflowResumeStatus.FAILED,
            f"Cannot resume session '{session_id}': workflow '{row.blueprint_name}' not found.",
        )
    steps = _standard_steps(loaded.definition)
    pending_ids = {step.id for step in steps}
    if checkpoint.pending_step_id not in pending_ids:
        return None, _resume_error(
            WorkflowResumeStatus.CORRUPT_CHECKPOINT,
            f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
        )
    return steps, None


@dataclass(frozen=True)
class _PreparedResume:
    checkpoint: RunCheckpoint
    steps: list[StepDefinition]


def _prepare_resume(session_id: str, cwd: Path, db: RunsDb) -> _PreparedResume | WorkflowResumeResult:
    row = db.get(session_id)
    row_error = _validate_resume_row(session_id, row)
    if row_error is not None or row is None:
        return row_error or _resume_error(
            WorkflowResumeStatus.NOT_FOUND,
            f"Workflow session '{session_id}' not found.",
        )
    checkpoint, checkpoint_error = _validate_checkpoint(session_id, row.checkpoint_json)
    if checkpoint_error is not None or checkpoint is None:
        return checkpoint_error or _resume_error(
            WorkflowResumeStatus.CORRUPT_CHECKPOINT,
            f"Cannot resume session '{session_id}': checkpoint is missing or corrupt.",
        )
    steps, steps_error = _load_resume_steps(session_id, row, checkpoint, cwd)
    if steps_error is not None or steps is None:
        return steps_error or _resume_error(
            WorkflowResumeStatus.FAILED,
            f"Cannot resume session '{session_id}': workflow '{row.blueprint_name}' not found.",
        )
    return _PreparedResume(checkpoint=checkpoint, steps=steps)


def _result_from_outcome(session_id: str, outcome: RunOutcome) -> WorkflowResumeResult:
    if outcome.status == RunStatus.PAUSED or outcome.ok:
        return WorkflowResumeResult(status=WorkflowResumeStatus.OK, warnings=list(outcome.warnings))
    return WorkflowResumeResult(
        status=WorkflowResumeStatus.FAILED,
        errors=[outcome.error_message or f"Workflow session '{session_id}' failed."],
        warnings=list(outcome.warnings),
    )


def resume_workflow(
    session_id: str,
    cwd: Path,
    *,
    failure_prompter: FailurePrompter | None = None,
    non_interactive: bool = False,
    observer: RunObserver | None = None,
) -> WorkflowResumeResult:
    """Load a paused workflow row, rebuild ``RunContext``, and re-enter ``run_steps``."""
    db = RunsDb(cwd)
    prepared = _prepare_resume(session_id, cwd, db)
    if isinstance(prepared, WorkflowResumeResult):
        return prepared

    db.update_status(session_id, RunStatus.RUNNING)
    outcome = run_steps(
        RunContext(
            steps=prepared.steps,
            cwd=cwd,
            use_sandbox=prepared.checkpoint.use_sandbox,
            keep=prepared.checkpoint.keep,
            agent=prepared.checkpoint.agent,
            observer=observer,
            inputs=prepared.checkpoint.inputs or None,
            non_interactive=non_interactive,
            failure_prompter=failure_prompter,
            pause_store=WorkflowPauseStore(cwd, session_id),
            resume_from=prepared.checkpoint,
        )
    )
    db.update_status(session_id, outcome.status, error_message=outcome.error_message)
    return _result_from_outcome(session_id, outcome)
