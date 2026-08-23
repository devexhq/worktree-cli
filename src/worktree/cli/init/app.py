import typer

from worktree.common.version import get_version
from worktree.core.context import get_cli_context

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
    cli_ctx = get_cli_context()
    init_command(cli_ctx=cli_ctx, tool_version=get_version(), overwrite=overwrite, repair=repair)
