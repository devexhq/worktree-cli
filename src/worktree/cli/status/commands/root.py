"""Status command implementation."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.cli.status.context import load_context
from worktree.common.utils import RichOutput

from ..renderers import render_status_table

_DEFAULT_RICH_OUTPUT = RichOutput()


def status_command(*, context: Context, rich_output: RichOutput | None = None) -> None:
    """Inspect active worktree configuration and repository context."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    try:
        ctx = load_context(context.cwd)
    except Exception as exc:
        output.error_panel("Context Error", str(exc))
        raise typer.Exit(code=1) from exc

    render_status_table(ctx, rich_output=output)
