"""Orchestration logic for ``wt task`` CLI commands."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from getworktree.common.fs import read_yaml_file
from getworktree.common.utils import RichOutput
from getworktree.core.catalog.services.inventory import (
    get_catalog_dir,
    scan_and_index_catalog,
)
from getworktree.core.db import (
    CatalogItemType,
    CatalogRecord,
    RunStatus,
    TaskRunRecord,
    TasksDb,
)
from getworktree.core.runtime import RunOutcome
from getworktree.core.step import StepDefinition, StepResult
from getworktree.core.task import (
    TaskDefinition,
    format_task_resolve_failure,
    format_task_run_failure,
    resolve_and_load_task,
    run_task,
)

from .models import (
    TaskBlueprintItem,
    TaskListCommandOutcome,
    TaskRunCommandOutcome,
    TaskShowCommandOutcome,
)
from .renderers import (
    render_task_list,
    render_task_run_success,
    render_task_show,
)

_DEFAULT_RICH_OUTPUT = RichOutput()
logger = logging.getLogger(__name__)


class CliRunObserver:
    """Observer adapter forwarding runtime step lifecycle events to RichOutput."""

    def __init__(self, output: RichOutput) -> None:
        self.output = output

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        """Report sandbox readiness to the CLI."""
        if active:
            self.output.info(f"Sandbox: Active ({path})")
        else:
            self.output.info("Sandbox: In-place (workspace)")

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Report step start progress to the CLI."""
        step_label = step.name or step.id
        cmd_info = f" (command: {step.run})" if step.run else ""
        self.output.info(f"[STEP {idx}/{total}] Executing {step_label}{cmd_info}...")

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the CLI."""
        step_label = result.step_id
        if result.ok:
            self.output.info(f"[bold green][STEP {idx}/{total}] {step_label} COMPLETED[/]")
            return
        msg = result.error_message or result.stderr or f"exit code {result.exit_code}"
        self.output.info(f"[bold red][STEP {idx}/{total}] {step_label} FAILED[/]: {msg}")

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention to the CLI."""
        if kept:
            self.output.info(f"Sandbox: Retained ({path})")
        else:
            self.output.info("Sandbox: Cleaned")


def _blueprint_from_record(
    record: CatalogRecord,
    cwd: Path | None,
) -> tuple[TaskBlueprintItem, str | None]:
    """Build a list item from a catalog record, loading TaskDefinition when possible."""
    load_result = resolve_and_load_task(record.name, cwd=cwd)
    if load_result.ok and isinstance(load_result.definition, TaskDefinition):
        definition = load_result.definition
        item = TaskBlueprintItem(
            name=record.name,
            description=definition.description,
            summary=definition.summary,
            sha=record.sha,
            path=str(record.path),
            use_sandbox=definition.use_sandbox,
        )
        return item, None

    warning: str | None = None
    if load_result.errors:
        warning = f"Failed to parse task blueprint '{record.path}': {load_result.errors[0]}"
    item = TaskBlueprintItem(
        name=record.name,
        description="",
        summary="",
        sha=record.sha,
        path=str(record.path),
        use_sandbox=True,
    )
    return item, warning


def _insert_running_record(
    cwd: Path | None,
    session_id: str,
    task_name: str,
) -> tuple[TaskRunRecord | None, list[str]]:
    """Insert a RUNNING task row; DB faults become warnings."""
    try:
        return TasksDb(cwd).insert(
            session_id=session_id,
            task_name=task_name,
            status=RunStatus.RUNNING,
        ), []
    except Exception as exc:
        logger.warning("Failed to record task run start in database: %s", exc)
        return None, [f"Failed to record task run start in database: {exc}"]


def _update_run_status(
    cwd: Path | None,
    session_id: str,
    status: RunStatus,
    error_message: str | None,
) -> tuple[TaskRunRecord | None, list[str]]:
    """Update task run status; DB faults become warnings."""
    try:
        return TasksDb(cwd).update_status(
            session_id=session_id,
            status=status,
            error_message=error_message,
        ), []
    except Exception as exc:
        logger.warning("Failed to update task run status in database: %s", exc)
        return None, [f"Failed to update task run status in database: {exc}"]


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
    updated_record: TaskRunRecord | None,
    warnings: list[str],
    output: RichOutput,
) -> TaskRunCommandOutcome:
    """Render run result and build the CLI outcome."""
    final_record = (
        updated_record
        or run_record
        or _fallback_run_record(
            session_id,
            name,
            run_outcome.status,
            run_outcome.error_message,
        )
    )

    if run_outcome.ok:
        render_task_run_success(final_record, rich_output=output)
        return TaskRunCommandOutcome(run_record=final_record, warnings=warnings)

    if run_outcome.status == RunStatus.CANCELLED:
        message = run_outcome.error_message or "Cancelled by user."
        output.error_panel("Task Run Cancelled", message)
        return TaskRunCommandOutcome(
            run_record=final_record,
            errors=[message],
            warnings=warnings,
        )

    message = format_task_run_failure(run_outcome)
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
    """List task blueprints under ``.worktree/catalog/tasks/`` and recorded runs."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    warnings: list[str] = []

    scan_result = scan_and_index_catalog(cwd=cwd)
    if not scan_result.ok:
        for err in scan_result.errors:
            output.error_panel("Task Catalog Scan Warning", err)

    task_records = [record for record in scan_result.items if record.item_type == CatalogItemType.TASK]
    items: list[TaskBlueprintItem] = []
    for record in task_records:
        item, warning = _blueprint_from_record(record, cwd)
        items.append(item)
        if warning:
            warnings.append(warning)

    runs: list[TaskRunRecord] = []
    try:
        runs = TasksDb(cwd).list()
    except Exception as exc:
        warnings.append(f"Failed to query task run history from database: {exc}")
        logger.warning("Failed to query task run history from database: %s", exc)

    render_task_list(items, runs=runs, rich_output=output)
    return TaskListCommandOutcome(
        items=items,
        runs=runs,
        errors=list(scan_result.errors),
        warnings=warnings,
    )


def task_show_command(
    name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskShowCommandOutcome:
    """Show details and definition content of a task blueprint."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    resolution = resolve_and_load_task(name, cwd=cwd)
    item = resolution.resolved
    if not resolution.ok or item is None:
        error_message = format_task_resolve_failure(resolution)
        output.error_panel("Task Show Failed", error_message)
        return TaskShowCommandOutcome(item=None, content=None, errors=[error_message])

    file_path = get_catalog_dir(cwd) / item.path
    yaml_file = read_yaml_file(file_path)
    if yaml_file.error or yaml_file.content is None:
        error_message = yaml_file.error or f"Failed to read file for task blueprint '{name}'."
        output.error_panel("Task Show Failed", error_message)
        return TaskShowCommandOutcome(item=item, content=None, errors=[error_message])

    content = yaml_file.content
    render_task_show(item, content, rich_output=output)
    return TaskShowCommandOutcome(item=item, content=content)


def task_run_command(
    name: str,
    cwd: Path | None = None,
    *,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    rich_output: RichOutput | None = None,
) -> TaskRunCommandOutcome:
    """Resolve a task blueprint, execute it via core runtime, and persist status."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()

    resolution = resolve_and_load_task(name, cwd=root)
    if not resolution.ok or not isinstance(resolution.definition, TaskDefinition):
        error_message = format_task_resolve_failure(resolution)
        output.error_panel("Task Run Failed", error_message)
        return TaskRunCommandOutcome(run_record=None, errors=[error_message])

    sid = session_id or f"task_{uuid.uuid4().hex[:8]}"
    run_record, warnings = _insert_running_record(cwd, sid, name)

    output.info(f"Running task '{name}'...")
    run_outcome = run_task(
        definition=resolution.definition,
        cwd=root,
        use_sandbox=not no_sandbox,
        keep=keep,
        agent=agent,
        observer=CliRunObserver(output),
    )

    updated_record, update_warnings = _update_run_status(
        cwd,
        sid,
        run_outcome.status,
        run_outcome.error_message,
    )
    warnings.extend(update_warnings)

    return _finalize_run_outcome(
        name=name,
        session_id=sid,
        run_outcome=run_outcome,
        run_record=run_record,
        updated_record=updated_record,
        warnings=warnings,
        output=output,
    )
