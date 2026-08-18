"""Rich table and console renderers for task CLI commands."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import RichOutput, enum_value
from worktree.core.db import TaskRunRecord

_DEFAULT_RICH_OUTPUT = RichOutput()


def build_task_runs_table(runs: list[TaskRunRecord]) -> Table:
    """Build the Rich table displaying recorded task execution history.

    Args:
        runs: List of TaskRunRecord instances.

    Returns:
        A Rich Table titled "Recorded Task Runs:" with SESSION ID, TASK NAME, STATUS, STARTED AT, COMPLETED AT.
    """
    table = Table(title="Recorded Task Runs:", title_justify="left", show_header=True)
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
    runs: list[TaskRunRecord] | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render recorded task run history (or an empty-state message)."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not runs:
        output.info("No recorded task runs found.")
    else:
        output.info(build_task_runs_table(runs))


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
