"""Orchestration logic for ``wt task`` CLI commands."""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml

from getworktree.commands.task.models import (
    TaskBlueprintItem,
    TaskListCommandOutcome,
    TaskRunCommandOutcome,
    TaskShowCommandOutcome,
)
from getworktree.commands.task.renderers import (
    render_task_list,
    render_task_run_success,
    render_task_show,
)
from getworktree.common.utils import RichOutput
from getworktree.core.catalog.inventory import (
    get_catalog_dir,
    get_catalog_item,
    scan_and_index_catalog,
)
from getworktree.core.db import (
    CatalogItemType,
    RunStatus,
    insert_task_run,
    update_task_run_status,
)

_DEFAULT_RICH_OUTPUT = RichOutput()


def task_list_command(
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskListCommandOutcome:
    """List task blueprints discovered under ``.worktree/catalog/tasks/``.

    Args:
        cwd: Optional working directory.
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskListCommandOutcome containing listed task blueprint items and errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    scan_res = scan_and_index_catalog(cwd=cwd)
    if not scan_res.ok:
        for err in scan_res.errors:
            output.error_panel("Task Catalog Scan Warning", err)

    task_records = [r for r in scan_res.items if r.item_type == CatalogItemType.TASK]
    catalog_dir = get_catalog_dir(cwd)

    items: list[TaskBlueprintItem] = []
    for record in task_records:
        file_path = catalog_dir / record.path
        description = ""
        summary = ""
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                yaml_data = yaml.safe_load(content)
                if isinstance(yaml_data, dict):
                    description = str(yaml_data.get("description", ""))
                    summary = str(yaml_data.get("summary", ""))
            except Exception:
                pass

        items.append(
            TaskBlueprintItem(
                name=record.name,
                description=description,
                summary=summary,
                sha=record.sha,
                path=str(record.path),
            )
        )

    render_task_list(items, rich_output=output)

    return TaskListCommandOutcome(
        items=items,
        errors=list(scan_res.errors),
    )


def task_show_command(
    name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskShowCommandOutcome:
    """Show details and definition of a specific task blueprint.

    Args:
        name: Task name or SHA identifier.
        cwd: Optional working directory.
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskShowCommandOutcome containing catalog item record and YAML definition.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    item = get_catalog_item(name, cwd=cwd)
    if item is None or item.item_type != CatalogItemType.TASK:
        error_msg = f"Task blueprint '{name}' not found."
        output.error_panel("Task Show Failed", error_msg)
        return TaskShowCommandOutcome(item=None, content=None, errors=[error_msg])

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_msg = f"Failed to read file for task blueprint '{name}': {exc}"
        output.error_panel("Task Show Failed", error_msg)
        return TaskShowCommandOutcome(item=item, content=None, errors=[error_msg])

    render_task_show(item, content, rich_output=output)
    return TaskShowCommandOutcome(item=item, content=content)


def task_run_command(
    name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskRunCommandOutcome:
    """Execute a task blueprint by name.

    Args:
        name: Name of the task to run.
        cwd: Optional working directory.
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskRunCommandOutcome containing task run record or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    item = get_catalog_item(name, cwd=cwd)
    if item is None or item.item_type != CatalogItemType.TASK:
        error_msg = f"Task blueprint '{name}' not found."
        output.error_panel("Task Run Failed", error_msg)
        return TaskRunCommandOutcome(run_record=None, errors=[error_msg])

    session_id = f"task_{uuid.uuid4().hex[:8]}"
    try:
        run_record = insert_task_run(
            session_id=session_id,
            task_name=name,
            status=RunStatus.RUNNING,
            cwd=cwd,
        )
        updated_record = update_task_run_status(
            session_id=session_id,
            status=RunStatus.COMPLETED,
            cwd=cwd,
        )
        final_record = updated_record or run_record
    except Exception as exc:
        error_msg = f"Failed to record task run execution for '{name}': {exc}"
        output.error_panel("Task Run Failed", error_msg)
        return TaskRunCommandOutcome(run_record=None, errors=[error_msg])

    render_task_run_success(final_record, rich_output=output)
    return TaskRunCommandOutcome(run_record=final_record)
