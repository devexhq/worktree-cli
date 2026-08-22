import typer

from .commands.root import config_set_command, config_show_command, config_validate_command

config_app = typer.Typer(
    name="config",
    help="Inspect, update, and validate Worktree CLI configuration.",
)


@config_app.command("show")
def config_show(ctx: typer.Context):
    """Display the full normalized effective configuration as JSON."""
    config_show_command()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(
        ...,
        help="Config key or nested dot-path (e.g. agent.model).",
    ),
    value: str = typer.Argument(
        ...,
        help="Value to store (string; typed parsing is separate).",
    ),
):
    """Set a configuration value by key or nested dot-path."""
    config_set_command(key, value)


@config_app.command("validate")
def config_validate(ctx: typer.Context):
    """Validate .worktree/config.json against the V1 schema and semantic rules."""
    config_validate_command()
