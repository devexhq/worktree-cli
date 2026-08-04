"""Typer CLI entrypoint for the Worktree (`wt`) command."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from getworktree.commands.config.command import (
    config_show_command,
    config_validate_command,
)
from getworktree.commands.init.command import init_command
from getworktree.commands.loop.command import loop_run_command, loop_show_command
from getworktree.commands.status.command import status_command

# Initialize a central styling console for high-utility layout parsing
console = Console()

# Package Metadata matching our PyPI footprint
__version__ = "0.1.1"

# Initialize Typer App with clean configuration defaults
app = typer.Typer(
    name="wt",
    help="Isolated git worktree developer loops and autonomous AI agent workspaces.",
    add_completion=True,
    rich_markup_mode="rich",
)

config_app = typer.Typer(
    name="config",
    help="Inspect and validate Worktree configuration.",
)
app.add_typer(config_app, name="config")

loop_app = typer.Typer(
    name="loop",
    help="Inspect and manage Worktree loop definitions.",
)
app.add_typer(loop_app, name="loop")


def print_welcome_banner():
    """Renders a highly scannable, developer-focused ASCII brand panel."""
    banner_text = Text()
    banner_text.append("🌳 Worktree CLI ", style="bold green")
    banner_text.append(f"v{__version__}\n", style="dim cyan")
    banner_text.append("Isolated Git Workspaces & Agent Loops", style="italic dim")

    console.print(
        Panel(banner_text, border_style="green", expand=False, padding=(1, 4))
    )


def version_callback(value: bool):
    """Callback function to handle explicit version printing flags."""
    if value:
        console.print(f"[bold green]Worktree CLI[/bold green] v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable extensive internal engineering telemetry logging.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print the current version of the Worktree CLI and exit.",
    ),
):
    """Global configuration wrapper managing shared application context."""
    # Stash verbose settings inside the runtime context dict for downstream commands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # If the developer types just 'wt' without a subcommand, render banner and help
    if ctx.invoked_subcommand is None:
        print_welcome_banner()
        console.print(ctx.get_help())
        raise typer.Exit()
    elif verbose:
        console.print(
            "[dim yellow][TELEMETRY] Global verbose tracking layer active.[/dim yellow]"
        )


@app.command(name="init")
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
    init_command(
        tool_version=__version__,
        overwrite=overwrite,
        repair=repair,
    )


@app.command(name="status")
def workspace_status(ctx: typer.Context):
    """Workspace Status."""
    status_command()


@config_app.command("show")
def config_show(ctx: typer.Context):
    """Display the full normalized effective configuration as JSON."""
    config_show_command()


@config_app.command("validate")
def config_validate(ctx: typer.Context):
    """Validate .worktree/config.json against the V1 schema and semantic rules."""
    config_validate_command()


@loop_app.command("show")
def loop_show(
    name: str = typer.Argument(..., help="Logical loop name to show."),
):
    """Show a human-readable summary of a loop definition."""
    loop_show_command(name)


@loop_app.command("run")
def loop_run(
    name: str = typer.Argument(..., help="Logical loop name to run."),
    max_attempts: int | None = typer.Option(
        None,
        "--max-attempts",
        help="Override effective max attempts (>= 1).",
        min=1,
    ),
    keep: bool = typer.Option(
        False,
        "--keep/--no-keep",
        help="When --keep, force retain the sandbox (auto_clean=False).",
    ),
    approve_each: bool | None = typer.Option(
        None,
        "--approve-each/--no-approve-each",
        help="Require (or skip) approval before each patch apply.",
    ),
    wip: bool = typer.Option(
        False,
        "--wip/--no-wip",
        help=(
            "Include uncommitted working-tree changes in the sandbox "
            "(tracked + untracked; not ignored)."
        ),
    ),
    dump_prompt: bool = typer.Option(
        False,
        "--dump-prompt/--no-dump-prompt",
        help=(
            "Dump provider-specific agent input to /tmp before each agent call "
            "(debugging aid)."
        ),
    ),
):
    """Run a loop in an isolated git worktree sandbox."""
    loop_run_command(
        name,
        max_attempts=max_attempts,
        keep=keep if keep else None,
        approve_each=approve_each,
        wip=wip,
        dump_prompt=dump_prompt,
    )


if __name__ == "__main__":
    app()
