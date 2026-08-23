import typer

from worktree.core.context import get_cli_context

from .commands.config_set import config_set_command
from .commands.config_show import config_show_command
from .commands.config_validate import config_validate_command

config_app = typer.Typer(
    name="config",
    help="Inspect, update, and validate Worktree CLI configuration.",
)


@config_app.command("show")
def config_show(ctx: typer.Context):
    """Display the full normalized effective configuration as JSON."""
    cli_ctx = get_cli_context()
    config_show_command(cli_ctx=cli_ctx)


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
    cli_ctx = get_cli_context()
    config_set_command(key, value, cli_ctx=cli_ctx)


@config_app.command("validate")
def config_validate(ctx: typer.Context):
    """Validate .worktree/config.json against the V1 schema and semantic rules."""
    cli_ctx = get_cli_context()
    config_validate_command(cli_ctx=cli_ctx)
