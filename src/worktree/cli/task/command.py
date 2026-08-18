"""Orchestration logic for ``wt task`` CLI commands."""

from __future__ import annotations

import logging
from pathlib import Path

from worktree.common.utils import RichOutput
from worktree.core.blueprint import (
    Blueprint,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintRenderer,
    BlueprintValidationError,
)
from worktree.core.catalog import Catalog
from worktree.core.db import RunStatus, TaskRunRecord, TasksDb
from worktree.core.engine import Engine, EngineInputError, EngineRuntimeError, RunRequest
from worktree.core.inputs import format_input_error_message
from worktree.core.runtime import FailurePrompter, RunOutcome

from .models import (
    TaskListCommandOutcome,
    TaskRunCommandOutcome,
)
from .observer import resolve_run_observer
from .prompter import CliFailurePrompter
from .renderers import (
    render_task_list,
    render_task_run_success,
)

_DEFAULT_RICH_OUTPUT = RichOutput()
logger = logging.getLogger(__name__)

_TASK_RENDERER = BlueprintRenderer(BlueprintKind.TASK)


def _fail_task_run(output: RichOutput, message: str) -> TaskRunCommandOutcome:
    """Render a Task Run Failed panel and return a record-less outcome."""
    output.error_panel("Task Run Failed", message)
    return TaskRunCommandOutcome(run_record=None, errors=[message])


def _load_run_record(cwd: Path, session_id: str) -> TaskRunRecord | None:
    """Return the persisted task row, or None when lookup fails."""
    try:
        return TasksDb(cwd).get(session_id)
    except Exception:
        return None


def _fallback_run_record(
    session_id: str,
    task_name: str,
    status: RunStatus,
    error_message: str | None,
) -> TaskRunRecord:
    return TaskRunRecord(
        id=-1,
        session_id=session_id,
        task_name=task_name,
        status=status,
        started_at="",
        completed_at=None,
        error_message=error_message,
    )


def _finalize_run_outcome(
    *,
    name: str,
    session_id: str,
    run_outcome: RunOutcome,
    run_record: TaskRunRecord | None,
    warnings: list[str],
    output: RichOutput,
) -> TaskRunCommandOutcome:
    """Render run result and build the CLI outcome."""
    final_record = run_record or _fallback_run_record(
        session_id,
        name,
        run_outcome.status,
        run_outcome.error_message,
    )

    if run_outcome.ok:
        render_task_run_success(final_record, rich_output=output)
        return TaskRunCommandOutcome(run_record=final_record, warnings=warnings)

    if run_outcome.status == RunStatus.PAUSED:
        message = run_outcome.error_message or "Task paused; checkpoint saved."
        output.info(message)
        return TaskRunCommandOutcome(run_record=final_record, warnings=warnings)

    if run_outcome.status == RunStatus.CANCELLED:
        message = run_outcome.error_message or "Cancelled by user."
        output.error_panel("Task Run Cancelled", message)
        return TaskRunCommandOutcome(
            run_record=final_record,
            errors=[message],
            warnings=warnings,
        )

    message = _TASK_RENDERER.render(run_outcome)
    output.error_panel("Task Run Failed", message)
    return TaskRunCommandOutcome(
        run_record=final_record,
        errors=[message],
        warnings=warnings,
    )


def task_list_command(
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskListCommandOutcome:
    """List recorded task runs. Blueprint inventory lives under ``wt catalog``."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    warnings: list[str] = []
    errors: list[str] = []

    runs: list[TaskRunRecord] = []
    try:
        runs = TasksDb(cwd).list()
    except Exception as exc:
        warnings.append(f"Failed to query task run history from database: {exc}")
        logger.warning("Failed to query task run history from database: %s", exc)

    render_task_list(runs=runs, rich_output=output)
    return TaskListCommandOutcome(
        runs=runs,
        errors=errors,
        warnings=warnings,
    )


def _resolve_failure_prompter(
    output: RichOutput,
    *,
    non_interactive: bool,
) -> tuple[bool, FailurePrompter | None]:
    """Build the CLI prompter and effective non-interactive flag (TTY-aware)."""
    if non_interactive:
        return True, None
    prompter = CliFailurePrompter(output, kind="task")
    if not prompter.is_interactive:
        return True, None
    return False, prompter


def task_run_command(
    name: str,
    cwd: Path | None = None,
    *,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    cli_args: list[str] | None = None,
    non_interactive: bool = False,
    rich_output: RichOutput | None = None,
) -> TaskRunCommandOutcome:
    """Resolve a task blueprint, execute it via Engine, and return the CLI outcome."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()
    catalog = Catalog(root)

    try:
        blueprint = Blueprint.load(name, catalog=catalog)
    except (BlueprintNotFoundError, BlueprintLoadError) as exc:
        return _fail_task_run(output, _TASK_RENDERER.render_resolve_failure([str(exc)]))
    except BlueprintValidationError as exc:
        return _fail_task_run(output, _TASK_RENDERER.render_validate_failure([str(exc)]))

    if blueprint.kind is not BlueprintKind.TASK:
        return _fail_task_run(
            output,
            f"Blueprint '{name}' is a {blueprint.kind.value}; wt task run requires a task.",
        )

    effective_non_interactive, failure_prompter = _resolve_failure_prompter(
        output,
        non_interactive=non_interactive,
    )
    output.info(f"Running task '{name}'...")
    observer = resolve_run_observer(output, non_interactive=effective_non_interactive)

    try:
        with observer:
            run_outcome = Engine(root).run(
                blueprint,
                RunRequest(
                    cli_args=cli_args,
                    use_sandbox=not no_sandbox,
                    keep=keep,
                    agent=agent,
                    session_id=session_id,
                    observer=observer,
                    failure_prompter=failure_prompter,
                    non_interactive=effective_non_interactive,
                ),
            )
    except EngineInputError as exc:
        return _fail_task_run(
            output,
            format_input_error_message(
                kind="task",
                name=name,
                result=exc.result,
                declarations=blueprint.inputs,
            ),
        )
    except EngineRuntimeError as exc:
        return _fail_task_run(output, str(exc))

    sid = run_outcome.session_id or ""
    for warning in run_outcome.warnings:
        output.info(warning)

    return _finalize_run_outcome(
        name=name,
        session_id=sid,
        run_outcome=run_outcome,
        run_record=_load_run_record(root, sid) if sid else None,
        warnings=list(run_outcome.warnings),
        output=output,
    )
