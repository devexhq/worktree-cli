"""Status command implementation."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.status import collect_status

from ..models import StatusCommandOutcome
from ..renderers import render_status_summary


def status_command(context: CliContext) -> StatusCommandOutcome:
    """Inspect active worktree configuration and repository context."""
    try:
        result = collect_status(context.cwd)
    except Exception as exc:
        context.output.add_error_panel("Status Error", str(exc))
        return StatusCommandOutcome(errors=[str(exc)])

    render_status_summary(result, output=context.output)
    return StatusCommandOutcome(result=result)
