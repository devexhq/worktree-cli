import typer

from getworktree.common.version import get_version

from .command import init_command

init_app = typer.Typer(name="init", help="Initialize Worktree CLI in the current directory.")


@init_app.command(name="init")
def init_workspace(
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
    init_command(tool_version=get_version(), overwrite=overwrite, repair=repair)
