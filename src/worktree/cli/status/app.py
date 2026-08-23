import typer

from worktree.cli.context import get_cli_context

from .commands.root import status_command

status_app = typer.Typer(
    name="status",
    help="Display configuration status for Worktree CLI.",
    invoke_without_command=True,
)


@status_app.callback(invoke_without_command=True)
def status_callback(ctx: typer.Context):
    """Display configuration status for Worktree CLI."""
    context = get_cli_context()
    status_command(context=context)
