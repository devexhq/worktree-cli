"""Rich table and console renderers for task CLI commands."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import RichOutput, enum_value
from worktree.core.blueprint.models import BlueprintKind
from worktree.core.blueprint.renderers import render_blueprint_run_success
from worktree.core.db import RunRecord
from worktree.core.runtime.observer import (
    LiveStepItem,
    _format_step_elapsed,
    _format_step_glyph,
    build_live_step_table,
)

_DEFAULT_RICH_OUTPUT = RichOutput()

__all__ = [
    "LiveStepItem",
    "_format_step_elapsed",
    "_format_step_glyph",
    "build_live_step_table",
    "build_task_runs_table",
    "render_task_list",
    "render_task_run_success",
]


def build_task_runs_table(runs: list[RunRecord]) -> Table:
    """Build the Rich table displaying recorded task execution history.

    Args:
        runs: List of RunRecord instances.

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
            run.blueprint_name,
            status_val,
            run.started_at or "-",
            run.completed_at or "-",
        )

    return table


def render_task_list(
    runs: list[RunRecord] | None = None,
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
    run_record: RunRecord,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render task run execution summary."""
    render_blueprint_run_success(run_record, BlueprintKind.TASK, rich_output=rich_output or _DEFAULT_RICH_OUTPUT)
