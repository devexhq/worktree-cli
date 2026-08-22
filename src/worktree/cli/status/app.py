import typer

from .commands.root import status_command

status_app = typer.Typer(
    name="status",
    help="Display configuration status for Worktree CLI.",
)


@status_app.command(name="status")
def workspace_status(ctx: typer.Context):
    """Workspace Status."""
    status_command()
