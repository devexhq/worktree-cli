"""Rendering helpers for `wt status` command."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import RichOutput, display_path
from worktree.core.status.models import WorktreeStatusResult


def render_status_summary(
    result: WorktreeStatusResult,
    *,
    output: RichOutput,
) -> None:
    """Render Rich terminal summary for WorktreeStatusResult."""
    table = Table(title="Worktree Workspace Status", title_justify="left", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    # Project Name
    project_name = (
        result.config.config.project.name
        if (result.config.config is not None and result.config.config.project.name)
        else "[dim]unnamed_project[/dim]"
    )
    table.add_row("Project Name", project_name)

    # Config Status
    config_rel = display_path(result.config.config_path, result.root_dir)
    table.add_row("Config Status", f"{result.config.status.value} ({config_rel})")

    # Active Git Branch
    branch_text = f"[yellow]{result.git.branch} (dirty)[/yellow]" if result.git.is_dirty else result.git.branch
    table.add_row("Active Git Branch", branch_text)

    # Agent Model
    model_text = (
        result.config.config.agent.model
        if (result.config.config is not None and result.config.config.agent.model)
        else "[dim]Not Configured[/dim]"
    )
    table.add_row("Agent Model", model_text)

    # Active Sandboxes
    table.add_row(
        "Active Sandboxes",
        f"{result.sandboxes.active_sandboxes} / {result.sandboxes.max_active_sandboxes} max",
    )

    # Catalog Items
    valid_items = result.catalog.total_items - result.catalog.invalid_items
    table.add_row("Catalog Items", f"{valid_items} valid / {result.catalog.total_items} total")

    output.add_line(table)

    if result.warnings:
        output.add_spacer()
        output.add_line("[yellow]⚠️ Configuration & Context Warnings:[/yellow]")
        for warning in result.warnings:
            output.add_dim_bullet(warning)
