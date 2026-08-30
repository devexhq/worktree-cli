from __future__ import annotations

import typer

from worktree.cli.context import CliContext

from .commands.root import status_command

status_app = typer.Typer(
    name="status",
    help="Display configuration status for Worktree CLI.",
    invoke_without_command=True,
)


@status_app.callback(invoke_without_command=True)
def status_callback(ctx: typer.Context) -> None:
    """Display configuration status for Worktree CLI."""
    context: CliContext = ctx.obj["context"]
    outcome = status_command(context)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
