"""Rich console renderers for execution history."""

from __future__ import annotations

import json
from datetime import datetime

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from worktree.common.utils import RichOutput, enum_value
from worktree.core.db import RunRecord, RunStatus
from worktree.core.runtime import RunCheckpoint, parse_checkpoint

_SESSION_SHOW_FIELDS = (
    "Session ID",
    "Blueprint Name",
    "Kind",
    "Branch",
    "Status",
    "Start time",
    "Completion time",
    "Duration",
)


def format_run_status(status: RunStatus | str) -> str:
    """Format a run lifecycle status with canonical CLI coloring."""
    raw_status = enum_value(status).lower()
    if raw_status == RunStatus.COMPLETED.value:
        return f"[green]{raw_status}[/green]"
    if raw_status == RunStatus.PAUSED.value:
        return f"[yellow]{raw_status}[/yellow]"
    if raw_status == RunStatus.FAILED.value:
        return f"[red]{raw_status}[/red]"
    if raw_status == RunStatus.CANCELLED.value:
        return f"[dim]{raw_status}[/dim]"
    if raw_status == RunStatus.RUNNING.value:
        return f"[cyan]{raw_status}[/cyan]"
    return raw_status


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Safely parse a timestamp string across supported ISO / SQLite formats."""
    if not timestamp_str or not timestamp_str.strip():
        return None
    cleaned = timestamp_str.strip()
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def format_run_duration(started_at: str | None, completed_at: str | None) -> str:
    """Calculate and format execution duration between start and completion timestamps."""
    start_time = _parse_timestamp(started_at)
    end_time = _parse_timestamp(completed_at)
    if start_time is None or end_time is None:
        return "-"

    total_seconds = (end_time - start_time).total_seconds()
    if total_seconds < 0:
        return "-"
    if total_seconds < 60:
        return f"{total_seconds:.2f}s"

    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}m {seconds:04.1f}s"


def build_history_table(runs: list[RunRecord]) -> Table:
    """Build the Rich table displaying execution history runs."""
    table = Table(title="Execution History", title_justify="left", show_header=True)
    table.add_column("SESSION ID", style="cyan", no_wrap=True)
    table.add_column("KIND", no_wrap=True)
    table.add_column("BLUEPRINT")
    table.add_column("STATUS")
    table.add_column("STARTED")
    table.add_column("COMPLETED")
    table.add_column("DURATION", justify="right")

    for row in runs:
        status_colored = format_run_status(row.status)
        duration = format_run_duration(row.started_at, row.completed_at)
        table.add_row(
            row.session_id,
            row.kind.value,
            row.blueprint_name,
            status_colored,
            row.started_at or "-",
            row.completed_at or "-",
            duration,
        )
    return table


def render_empty_history(*, output: RichOutput) -> None:
    """Render the empty-state line when no runs match."""
    output.add_line("No execution history found.")


def render_history_list(runs: list[RunRecord], *, output: RichOutput) -> None:
    """Render empty state or execution history table."""
    if not runs:
        render_empty_history(output=output)
        return
    output.add_line(build_history_table(runs))


def render_not_initialized(errors: list[str], *, output: RichOutput) -> None:
    """Render the not-initialized error panel for history commands."""
    output.render_not_initialized(
        errors,
        fix_hint="run `wt init` to initialize the workspace",
    )


def render_history_not_found(session_id: str, *, output: RichOutput) -> None:
    """Render the not-found error panel for history show."""
    message = f"Session '{session_id}' not found.\nFix:\n- run `wt history` to view past sessions"
    output.add_error_panel("Session Not Found", message)


def _build_metadata_table(run: RunRecord) -> Table:
    """Build key/value table for session metadata."""
    duration = format_run_duration(run.started_at, run.completed_at)
    values = {
        "Session ID": run.session_id,
        "Blueprint Name": run.blueprint_name,
        "Kind": run.kind.value,
        "Branch": run.branch_name if run.branch_name else "-",
        "Status": format_run_status(run.status),
        "Start time": run.started_at or "-",
        "Completion time": run.completed_at or "-",
        "Duration": duration,
    }

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="bold")
    table.add_column()
    for field in _SESSION_SHOW_FIELDS:
        table.add_row(f"{field}:", values[field])
    return table


def _build_step_results_table(checkpoint: RunCheckpoint) -> Table | None:
    """Build a sub-table summarizing recorded step results in a checkpoint."""
    if not checkpoint.step_results:
        return None
    table = Table(title="Step Results", title_justify="left", show_header=True)
    table.add_column("Step ID", style="bold")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Error")

    for step_result in checkpoint.step_results:
        status_style = "green" if step_result.ok else "red"
        status_label = f"[{status_style}]{step_result.status}[/{status_style}]"
        step_duration = f"{step_result.duration_seconds:.2f}s"
        error_label = step_result.error_message or "-"
        table.add_row(step_result.step_id, status_label, step_duration, error_label)
    return table


def _render_checkpoint_panel(checkpoint_json: str, *, output: RichOutput) -> None:
    """Render checkpoint metadata and step details or pretty JSON fallback."""
    checkpoint = parse_checkpoint(checkpoint_json)
    if checkpoint is None:
        try:
            formatted_json = json.dumps(json.loads(checkpoint_json), indent=2)
            output.add_line(Panel(Syntax(formatted_json, "json"), title="Checkpoint JSON", border_style="cyan"))
        except Exception:
            output.add_line(Panel(checkpoint_json, title="Checkpoint Data", border_style="cyan"))
        return

    checkpoint_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    checkpoint_table.add_column(style="bold")
    checkpoint_table.add_column()
    checkpoint_table.add_row("Pending Step ID:", checkpoint.pending_step_id)
    checkpoint_table.add_row("Next Step Index:", str(checkpoint.next_step_index))
    if checkpoint.diagnostic:
        checkpoint_table.add_row("Diagnostic:", checkpoint.diagnostic)

    output.add_line(Panel(checkpoint_table, title="Checkpoint Details", border_style="cyan"))

    step_table = _build_step_results_table(checkpoint)
    if step_table is not None:
        output.add_line(step_table)


def render_history_show(run: RunRecord, *, output: RichOutput) -> None:
    """Render granular session metadata, errors, and checkpoint contents."""
    metadata_table = _build_metadata_table(run)
    output.add_line(Panel(metadata_table, title=f"Session Metadata: {run.session_id}", border_style="blue"))

    if run.error_message:
        output.add_line(Panel(run.error_message, title="Error Details", border_style="red"))

    if run.checkpoint_json:
        _render_checkpoint_panel(run.checkpoint_json, output=output)
