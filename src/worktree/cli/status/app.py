from __future__ import annotations

from pathlib import Path

import typer

from worktree.cli.context import CliContext
from worktree.common.utils import RichOutput
from worktree.core.db.facade import WorktreeDb

from .commands.root import status_command

status_app = typer.Typer(
    name="status",
    help="Display configuration status for Worktree CLI.",
    invoke_without_command=True,
)


@status_app.callback(invoke_without_command=True)
def status_callback(ctx: typer.Context) -> None:
    """Display configuration status for Worktree CLI."""
    context: CliContext | None = ctx.obj.get("context") if ctx.obj else None
    if context is None:
        cwd = Path.cwd()
        context = CliContext(cwd=cwd, db=WorktreeDb(path=cwd), output=RichOutput())
    outcome = status_command(context)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
