from pathlib import Path

import typer

from worktree.cli.context import CliContext
from worktree.common.utils import RichOutput
from worktree.common.version import get_version
from worktree.core.db.facade import WorktreeDb

from .commands.root import init_command

init_app = typer.Typer(name="init", help="Initialize Worktree CLI in the current directory.")


@init_app.callback(invoke_without_command=True)
def init_callback(
    ctx: typer.Context,
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing config with fresh V1 defaults (destructive).",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Add missing required config keys without overwriting user values.",
    ),
):
    """Provision a secure local hidden folder path and tracking schemas."""
    cwd = Path.cwd()
    context = CliContext(cwd=cwd, db=WorktreeDb(path=cwd), output=RichOutput())
    outcome = init_command(context, tool_version=get_version(), overwrite=overwrite, repair=repair)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
