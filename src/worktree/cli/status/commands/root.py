"""Status command implementation."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.cli.status.context import load_context

from ..renderers import render_status_table


def status_command(*, context: Context) -> None:
    """Inspect active worktree configuration and repository context."""
    output = context.output

    try:
        ctx = load_context(context.cwd)
    except Exception as exc:
        output.error_panel("Context Error", str(exc))
        output.print()
        raise typer.Exit(code=1) from exc

    render_status_table(ctx, output=output)
    output.print()
