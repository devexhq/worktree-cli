"""Status command implementation."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.engine import format_reconciliation_warning, reconcile_stale_runs
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
    try:
        reconciled = reconcile_stale_runs(context.db)
        warning_message = format_reconciliation_warning(reconciled)
    except Exception:
        warning_message = None

    result = Status(context.cwd).collect()

    if warning_message and warning_message not in result.warnings:
        result.warnings.insert(0, warning_message)

    ui_dispatcher.dispatch(result, output_format=output_format)
    return StatusCommandOutcome(result=result)
