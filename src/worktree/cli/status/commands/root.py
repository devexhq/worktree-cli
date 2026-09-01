"""Status command implementation."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.engine import reconcile_stale_runs
from worktree.core.status import Status

from ..models import StatusCommandOutcome


def status_command(
    context: CliContext,
    output_format: str = "terminal",
) -> StatusCommandOutcome:
    """Inspect active worktree configuration and repository context.

    Args:
        context: CLI context instance.
        output_format: Presentation format ("terminal" or "json").
    """
    reconciliation_result = reconcile_stale_runs(context.db)

    result = Status(context.cwd).collect()

    if reconciliation_result.warning and reconciliation_result.warning not in result.warnings:
        result.warnings.insert(0, reconciliation_result.warning)

    ui_dispatcher.dispatch(result, output_format=output_format)
    return StatusCommandOutcome(result=result)
