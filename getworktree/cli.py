"""Typer CLI entrypoint for the Worktree (`wt`) command."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from getworktree.commands.config.command import config_show_command
from getworktree.commands.init.command import init_command
from getworktree.commands.loop.command import loop_command
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
    help="Inspect effective Worktree configuration.",
)
app.add_typer(config_app, name="config")


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


@app.command(name="loop")
def loop(
    command: str = typer.Argument(..., help="Target test or build command string."),
):
    """Run command in isolated sandbox and extract error diagnostic payloads."""
    loop_command(command)


if __name__ == "__main__":
    app()
