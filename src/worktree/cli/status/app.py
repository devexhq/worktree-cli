from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config import Config
from worktree.core.db.facade import WorktreeDb

from .commands.root import status_command
from .formatters import register_status_formatters

register_status_formatters()

status_app = typer.Typer(
    name="status",
    help="Display configuration status for Worktree CLI.",
    invoke_without_command=True,
)


@status_app.callback(invoke_without_command=True)
def status_callback(
    ctx: typer.Context,
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
) -> None:
    """Display configuration status for Worktree CLI."""
    context: CliContext | None = ctx.obj.get("context") if ctx.obj else None
    if context is None:
        target_path = ctx.obj.get("path") if ctx.obj else None
        fs = Filesystem.configure(target_path)
        Config.configure(target_path)
        cwd = fs.root_dir
        context = CliContext(cwd=cwd, db=WorktreeDb(path=cwd), fs=fs)
    status_command(context, output_format=format)
