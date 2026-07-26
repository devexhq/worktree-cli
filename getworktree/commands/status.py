"""getworktree/commands/status.py."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from getworktree.core.config_manager import display_context_warnings, load_context

console = Console()


def status_command():
    """Inspect active worktree configuration and repository context."""
    try:
        ctx = load_context(Path.cwd())
    except Exception as e:
        console.print(f"[bold red]Context Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    # Context Overview Table
    table = Table(title="Worktree Local Workspace Status", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Project Name", ctx.config.project_name)
    table.add_row("Config Version", ctx.config.version)
    table.add_row("Active Git Branch", ctx.current_branch)
    table.add_row("Model Path", ctx.config.model_path or "[dim]Not Configured[/dim]")
    table.add_row("Auto Clean Sandboxes", str(ctx.config.sandbox.auto_clean))
    table.add_row("Max Background Runs", str(ctx.config.sandbox.max_background_runs))

    console.print(table)
    console.print()

    # Print active warnings if any exist
    display_context_warnings(ctx)
