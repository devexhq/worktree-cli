"""Shared Rich tables and formatting helpers for history formatters."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from worktree.cli.ui.formatters.history.history_views import (
    CheckpointDetailsView,
    CheckpointStepView,
    RunSummaryView,
)
from worktree.common.utils import enum_value
from worktree.core.db import RunRecord, RunStatus
from worktree.core.runtime import RunCheckpoint, parse_checkpoint
from worktree.core.step import StepResult

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


def format_run_duration(duration_seconds: float | None) -> str:
    """Format elapsed seconds into canonical human-readable CLI duration string."""
    if duration_seconds is None or duration_seconds < 0:
        return "-"
    if duration_seconds < 60:
        return f"{duration_seconds:.2f}s"

    minutes = int(duration_seconds // 60)
    seconds = duration_seconds % 60
    return f"{minutes}m {seconds:04.1f}s"


def build_run_summary(run: RunRecord) -> RunSummaryView:
    """Derive a presentation-ready RunSummaryView from a RunRecord domain model."""
    return RunSummaryView(
        session_id=run.session_id,
        kind=enum_value(run.kind),
        blueprint_name=run.blueprint_name,
        status=enum_value(run.status),
        branch_name=run.branch_name if run.branch_name else None,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
    )


def build_history_table(runs: Sequence[RunSummaryView | RunRecord]) -> Table:
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
        duration = format_run_duration(row.duration_seconds)
        table.add_row(
            row.session_id,
            enum_value(row.kind),
            row.blueprint_name,
            status_colored,
            row.started_at or "-",
            row.completed_at or "-",
            duration,
        )
    return table


def build_metadata_table(run: RunSummaryView | RunRecord) -> Table:
    """Build key/value table for session metadata."""
    duration = format_run_duration(run.duration_seconds)
    values = {
        "Session ID": run.session_id,
        "Blueprint Name": run.blueprint_name,
        "Kind": enum_value(run.kind),
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


def build_step_results_table(checkpoint: CheckpointDetailsView | RunCheckpoint) -> Table | None:
    """Build a sub-table summarizing recorded step results in a checkpoint."""
    if not checkpoint.step_results:
        return None
    table = Table(title="Step Results", title_justify="left", show_header=True)
    table.add_column("Step ID", style="bold")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Error")

    for step_result in checkpoint.step_results:
        ok = step_result.ok if isinstance(step_result, StepResult) else step_result.status in ("completed", "ignored")
        status_style = "green" if ok else "red"
        status_label = f"[{status_style}]{step_result.status}[/{status_style}]"
        step_duration = f"{step_result.duration_seconds:.2f}s"
        error_label = step_result.error_message or "-"
        table.add_row(step_result.step_id, status_label, step_duration, error_label)
    return table


def build_checkpoint_view_renderables(
    checkpoint: CheckpointDetailsView | None,
    checkpoint_raw: str | None = None,
) -> list[Panel | Table]:
    """Build checkpoint metadata and step details renderables or pretty JSON fallback."""
    if checkpoint is not None:
        checkpoint_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        checkpoint_table.add_column(style="bold")
        checkpoint_table.add_column()
        checkpoint_table.add_row("Pending Step ID:", checkpoint.pending_step_id)
        checkpoint_table.add_row("Next Step Index:", str(checkpoint.next_step_index))
        if checkpoint.diagnostic:
            checkpoint_table.add_row("Diagnostic:", checkpoint.diagnostic)

        renderables: list[Panel | Table] = [Panel(checkpoint_table, title="Checkpoint Details", border_style="cyan")]
        step_table = build_step_results_table(checkpoint)
        if step_table is not None:
            renderables.append(step_table)
        return renderables

    if checkpoint_raw is not None:
        try:
            formatted_json = json.dumps(json.loads(checkpoint_raw), indent=2)
            return [Panel(Syntax(formatted_json, "json"), title="Checkpoint JSON", border_style="cyan")]
        except Exception:
            return [Panel(checkpoint_raw, title="Checkpoint Data", border_style="cyan")]

    return []


def build_checkpoint_renderables(checkpoint_json: str) -> list[Panel | Table]:
    """Build checkpoint metadata and step details renderables or pretty JSON fallback."""
    checkpoint = parse_checkpoint(checkpoint_json)
    if checkpoint is None:
        return build_checkpoint_view_renderables(None, checkpoint_raw=checkpoint_json)
    return build_checkpoint_view_renderables(
        CheckpointDetailsView(
            pending_step_id=checkpoint.pending_step_id,
            next_step_index=checkpoint.next_step_index,
            diagnostic=checkpoint.diagnostic,
            step_results=[
                CheckpointStepView(
                    step_id=step.step_id,
                    status=step.status,
                    duration_seconds=step.duration_seconds,
                    error_message=step.error_message,
                )
                for step in checkpoint.step_results
            ],
        )
    )
