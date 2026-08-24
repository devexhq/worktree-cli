"""Typer CLI entrypoint for the Worktree (`wt`) command."""

import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from worktree.cli.catalog.app import catalog_app
from worktree.cli.config.app import config_app
from worktree.cli.context import CliContext
from worktree.cli.history.app import history_app
from worktree.cli.init.app import init_app
from worktree.cli.resume.app import register_resume_command
from worktree.cli.run.app import register_run_command
from worktree.cli.sandbox.app import sandbox_app
from worktree.cli.status.app import status_app
from worktree.common.utils import RichOutput
from worktree.common.version import get_version

# Initialize a central styling console for high-utility layout parsing
console = Console()

# Package Metadata matching our PyPI footprint
__version__ = get_version()

# Initialize Typer App with clean configuration defaults
app = typer.Typer(
    name="wt",
    help="Isolated git worktree developer workflows and autonomous AI agent workspaces.",
    add_completion=True,
    rich_markup_mode="rich",
)

app.add_typer(catalog_app, name="catalog")
app.add_typer(config_app, name="config")
app.add_typer(history_app, name="history")
app.add_typer(init_app, name="init")
register_resume_command(app)
register_run_command(app)
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(status_app, name="status")


def print_welcome_banner():
    """Renders a highly scannable, developer-focused ASCII brand panel."""
    banner_text = Text()
    banner_text.append("🌳 Worktree CLI ", style="bold green")
    banner_text.append(f"v{__version__}\n", style="dim cyan")
    banner_text.append("Isolated Git Workspaces & Agent Workflows", style="italic dim")

    console.print(Panel(banner_text, border_style="green", expand=False, padding=(1, 4)))


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

    # 1. Handle base commands
    if ctx.invoked_subcommand is None:
        print_welcome_banner()
        console.print(ctx.get_help())
        raise typer.Exit()
    elif verbose:
        console.print("[dim yellow][TELEMETRY] Global verbose tracking layer active.[/dim yellow]")

    # 2. Edge validation & exclusion list
    excluded_commands = {"init", "install"}
    if ctx.invoked_subcommand not in excluded_commands:
        context = CliContext.build()
        if context is None:
            # Output already handled in CliContext.build
            raise typer.Exit(code=1)
        ctx.obj["context"] = context


def run_cli() -> None:
    """Main entrypoint with global crash protection."""
    try:
        app()
    except typer.Exit:
        # Allow intentional Typer exits (like version_callback or help) to pass through normally
        raise
    except Exception as exc:
        # Global Catch-All for unexpected bugs (e.g., missing record.id)
        output = RichOutput()
        output.add_error("A fatal unexpected error occurred.")
        output.add_line(f"Details: {exc!s}")
        output.print()
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
