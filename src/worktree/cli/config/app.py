import typer

from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config import Config
from worktree.core.db.facade import WorktreeDb

from .commands.config_set import config_set_command
from .commands.config_show import config_show_command
from .commands.config_validate import config_validate_command
from .formatters import register_config_formatters

register_config_formatters()

config_app = typer.Typer(
    name="config",
    help="Inspect, update, and validate Worktree CLI configuration.",
)


def _get_or_build_context(ctx: typer.Context) -> CliContext:
    """Retrieve existing context or build a direct context without strict config gating."""
    context: CliContext | None = ctx.obj.get("context") if ctx.obj else None
    if context is not None:
        return context
    target_path = ctx.obj.get("path") if ctx.obj else None
    fs = Filesystem.configure(target_path)
    Config.configure(target_path)
    cwd = fs.root_dir
    return CliContext(cwd=cwd, db=WorktreeDb(path=cwd), fs=fs)


@config_app.command("show")
def config_show(
    ctx: typer.Context,
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Display the full normalized effective configuration as JSON."""
    context = _get_or_build_context(ctx)
    outcome = config_show_command(context, output_format=format)
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
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Set a configuration value by key or nested dot-path."""
    context = _get_or_build_context(ctx)
    outcome = config_set_command(context, key, value, output_format=format)
    if not outcome.ok:
        raise typer.Exit(code=1)


@config_app.command("validate")
def config_validate(
    ctx: typer.Context,
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Validate .worktree/config.json against the V1 schema and semantic rules."""
    context = _get_or_build_context(ctx)
    outcome = config_validate_command(context, output_format=format)
    if not outcome.ok:
        raise typer.Exit(code=1)
