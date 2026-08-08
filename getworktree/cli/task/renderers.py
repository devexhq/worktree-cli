"""Rich table and console renderers for task CLI commands."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.table import Table

from getworktree.common.utils import RichOutput, enum_value
from getworktree.core.db import CatalogRecord, TaskRunRecord

from .models import TaskBlueprintItem

_DEFAULT_RICH_OUTPUT = RichOutput()


def build_task_table(items: list[TaskBlueprintItem]) -> Table:
    """Build the Rich table displaying available task blueprints.

    Args:
        items: List of TaskBlueprintItem instances.

    Returns:
        A Rich Table titled "Available Tasks:" with NAME, DESCRIPTION, SUMMARY columns.
    """
    table = Table(title="Available Tasks:", show_header=True)
    table.add_column("NAME", no_wrap=True)
    table.add_column("DESCRIPTION")
    table.add_column("SUMMARY")

    for item in items:
        table.add_row(
            item.name,
            item.description,
            item.summary,
        )

    return table


def build_task_runs_table(runs: list[TaskRunRecord]) -> Table:
    """Build the Rich table displaying recorded task execution history.

    Args:
        runs: List of TaskRunRecord instances.

    Returns:
        A Rich Table titled "Recorded Task Runs:" with SESSION ID, TASK NAME, STATUS, STARTED AT, COMPLETED AT.
    """
    table = Table(title="Recorded Task Runs:", show_header=True)
    table.add_column("SESSION ID", no_wrap=True)
    table.add_column("TASK NAME")
    table.add_column("STATUS")
    table.add_column("STARTED AT")
    table.add_column("COMPLETED AT")

    for run in runs:
        status_val = enum_value(run.status)
        table.add_row(
            run.session_id,
            run.task_name,
            status_val,
            run.started_at or "-",
            run.completed_at or "-",
        )

    return table


def render_task_list(
    items: list[TaskBlueprintItem],
    runs: list[TaskRunRecord] | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state, available tasks table, and recorded task run history."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not items and not runs:
        output.info("No task blueprints found.")
    else:
        if items:
            output.info(build_task_table(items))
        if runs:
            output.info(build_task_runs_table(runs))


def render_task_show(
    item: CatalogRecord,
    content: str,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render detailed view of a task blueprint including definition content."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    rel_path = Path(".worktree") / "catalog" / item.path
    output.info(f"[bold green]Task Blueprint:[/]   {item.name} ({item.sha})")
    output.info(f"[bold green]Path:[/]           {rel_path}")
    output.info(f"[bold green]Checksum:[/]       {item.checksum}")
    output.info("\n[bold cyan]Definition:[/]")
    if content:
        output.info(Syntax(content.strip(), "yaml"))


def render_task_run_success(
    run_record: TaskRunRecord,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render task run execution summary."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    output.info(
        f"[bold green]Task Run Completed:[/] {run_record.task_name} (session: {run_record.session_id}, status: {run_record.status.value})"
    )
