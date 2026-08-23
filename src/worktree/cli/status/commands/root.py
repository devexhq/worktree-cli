"""Status command implementation."""

from worktree.cli.context import Context
from worktree.cli.status.context import load_context

from ..models import StatusCommandOutcome
from ..renderers import render_status_table


def status_command(*, context: Context) -> StatusCommandOutcome:
    """Inspect active worktree configuration and repository context."""
    output = context.output

    try:
        ctx = load_context(context.cwd)
    except Exception as exc:
        output.error_panel("Context Error", str(exc))
        return StatusCommandOutcome(ok=False, errors=[str(exc)])

    render_status_table(ctx, output=output)
    return StatusCommandOutcome(ok=True, context=ctx)
