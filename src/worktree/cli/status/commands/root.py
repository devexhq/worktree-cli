"""Status command implementation."""

from __future__ import annotations

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.context import load_context
from worktree.core.config.models import CliContext

from ..renderers import render_status_table

_DEFAULT_RICH_OUTPUT = RichOutput()


def status_command(*, cli_ctx: CliContext, rich_output: RichOutput | None = None) -> None:
    """Inspect active worktree configuration and repository context."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    try:
        ctx = load_context(cli_ctx.cwd)
    except Exception as exc:
        output.error_panel("Context Error", str(exc))
        raise typer.Exit(code=1) from exc

    render_status_table(ctx, rich_output=output)
