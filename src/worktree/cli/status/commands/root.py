"""Status command implementation."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.engine import format_reconciliation_warning, reconcile_stale_runs
from worktree.core.status import Status

from ..models import StatusCommandOutcome
from ..renderers import render_status_summary


def status_command(context: CliContext) -> StatusCommandOutcome:
    """Inspect active worktree configuration and repository context."""
    try:
        reconciled = reconcile_stale_runs(context.db)
        warning_message = format_reconciliation_warning(reconciled)
        if warning_message:
            context.output.add_warning(warning_message)
    except Exception:
        pass

    try:
        result = Status(context.cwd).collect()
    except Exception as exc:
        context.output.add_error_panel("Status Error", str(exc))
        return StatusCommandOutcome(errors=[str(exc)])

    render_status_summary(result, output=context.output)
    return StatusCommandOutcome(result=result)
