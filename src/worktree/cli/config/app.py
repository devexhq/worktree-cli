import typer

from worktree.cli.context import CliContext

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
    context: CliContext = ctx.obj["context"]
    outcome = config_show_command(context)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)


@config_app.command("set")
def config_set(
    ctx: typer.Context,
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
    context: CliContext = ctx.obj["context"]
    outcome = config_set_command(context, key, value)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)


@config_app.command("validate")
def config_validate(ctx: typer.Context):
    """Validate .worktree/config.json against the V1 schema and semantic rules."""
    context: CliContext = ctx.obj["context"]
    outcome = config_validate_command(context)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
