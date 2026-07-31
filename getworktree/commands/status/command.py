"""getworktree/commands/status.py."""

from pathlib import Path

import typer
from rich.table import Table

from getworktree.common.utils import RichOutput
from getworktree.core.config.context import display_context_warnings, load_context

rich_output = RichOutput()


def status_command():
    """Inspect active worktree configuration and repository context."""
    try:
        ctx = load_context(Path.cwd())
    except Exception as e:
        rich_output.error(f"[bold red]Context Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    table = Table(title="Worktree Local Workspace Status", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Project Name", ctx.config.project.name)
    table.add_row("Config Version", str(ctx.config.version))
    table.add_row("Active Git Branch", ctx.current_branch)
    table.add_row("Agent Model", ctx.config.agent.model or "[dim]Not Configured[/dim]")
    table.add_row("Auto Clean Sandboxes", str(ctx.config.sandbox.auto_clean))
    table.add_row("Max Active Sandboxes", str(ctx.config.sandbox.max_active_sandboxes))

    rich_output.info(table)
    rich_output.spacer()

    display_context_warnings(ctx)
