"""Rendering helpers for `wt status` command."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import RichOutput
from worktree.core.config.context import display_context_warnings
from worktree.core.config.models import WorktreeContext

_DEFAULT_RICH_OUTPUT = RichOutput()


def render_status_table(ctx: WorktreeContext, *, rich_output: RichOutput | None = None) -> None:
    """Render workspace context summary table and any active warnings."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    table = Table(title="Worktree Local Workspace Status", title_justify="left", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Project Name", ctx.config.project.name)
    table.add_row("Config Version", str(ctx.config.version))
    table.add_row("Active Git Branch", ctx.current_branch)
    table.add_row("Agent Model", ctx.config.agent.model or "[dim]Not Configured[/dim]")
    table.add_row("Max Active Sandboxes", str(ctx.config.sandbox.max_active_sandboxes))

    output.info(table)
    output.spacer()

    display_context_warnings(ctx)
