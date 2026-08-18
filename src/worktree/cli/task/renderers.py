"""Rich table and console renderers for task CLI commands."""

from __future__ import annotations

import time
from dataclasses import dataclass

from rich.table import Table

from worktree.common.utils import RichOutput, enum_value
from worktree.core.db import TaskRunRecord

_DEFAULT_RICH_OUTPUT = RichOutput()


@dataclass
class LiveStepItem:
    """Tracked live execution step state for Rich Live output."""

    idx: int
    total: int
    name: str
    command: str | None = None
    status: str = "pending"
    start_time: float | None = None
    duration: float | None = None
    error_message: str | None = None


def _format_step_glyph(status: str) -> str:
    if status == "running":
        return "[bold yellow]•[/bold yellow]"
    if status == "completed":
        return "[bold green]✔[/bold green]"
    if status == "failed":
        return "[bold red]✖[/bold red]"
    return "[dim]○[/dim]"


def _format_step_elapsed(item: LiveStepItem, now: float) -> str:
    if item.status == "running" and item.start_time is not None:
        return f"{now - item.start_time:.1f}s"
    if item.duration is not None:
        return f"{item.duration:.2f}s"
    return "-"


def build_live_step_table(
    steps: list[LiveStepItem],
    *,
    sandbox_info: str | None = None,
    now: float | None = None,
) -> Table:
    """Build the Rich table displaying dynamic step execution progress.

    Args:
        steps: List of LiveStepItem instances.
        sandbox_info: Optional string describing sandbox state.
        now: Optional monotonic timestamp for testing.

    Returns:
        A Rich Table displaying step execution status, names, commands, and elapsed time.
    """
    title = f"Task Execution Progress ({sandbox_info})" if sandbox_info else "Task Execution Progress"
    table = Table(title=title, title_justify="left", show_header=True)
    table.add_column("Status", width=6, justify="center")
    table.add_column("Step")
    table.add_column("Command")
    table.add_column("Elapsed", justify="right")

    current_time = now if now is not None else time.monotonic()
    for item in steps:
        glyph = _format_step_glyph(item.status)
        elapsed = _format_step_elapsed(item, current_time)
        cmd_display = item.command or "[dim]-[/dim]"
        step_label = f"[{item.idx}/{item.total}] {item.name}"
        table.add_row(glyph, step_label, cmd_display, elapsed)

    return table


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
