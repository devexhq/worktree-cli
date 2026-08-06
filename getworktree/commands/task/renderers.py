"""Rich table and console renderers for task CLI commands."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.table import Table

from getworktree.commands.task.models import TaskBlueprintItem
from getworktree.common.utils import RichOutput
from getworktree.core.db import CatalogRecord, TaskRunRecord

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


def render_task_list(
    items: list[TaskBlueprintItem],
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state or available tasks table."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not items:
        output.info("No task blueprints found.")
    else:
        output.info(build_task_table(items))


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
