"""Shared formatting helpers and tables for status formatters."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import display_path
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.status.models import WorktreeStatusResult

CONFIG_STATUS_DISPLAY: dict[ConfigLoadStatus, str] = {
    ConfigLoadStatus.OK: "ok",
    ConfigLoadStatus.NOT_FOUND: "[yellow]CONFIG_NOT_FOUND[/yellow]",
    ConfigLoadStatus.MALFORMED_JSON: "[red]CONFIG_MALFORMED_JSON[/red]",
    ConfigLoadStatus.SCHEMA_INVALID: "[red]CONFIG_SCHEMA_INVALID[/red]",
    ConfigLoadStatus.ROOT_NOT_OBJECT: "[red]CONFIG_ROOT_NOT_OBJECT[/red]",
    ConfigLoadStatus.PATH_IS_DIRECTORY: "[red]PATH_IS_DIRECTORY[/red]",
    ConfigLoadStatus.UNREADABLE: "[red]CONFIG_UNREADABLE[/red]",
}


def get_table_title(result: WorktreeStatusResult) -> str:
    """Determine the status table title based on workspace initialization and health."""
    if not result.is_initialized or result.config.status == ConfigLoadStatus.NOT_FOUND:
        return "Worktree Workspace Status (Uninitialized)"
    if not result.ok:
        return "Worktree Workspace Status (Degraded)"
    return "Worktree Workspace Status"


def format_project_name(result: WorktreeStatusResult) -> str:
    """Format project name with uninitialized fallback."""
    if result.config.config is not None and result.config.config.project.name:
        return result.config.config.project.name
    if result.config.raw is not None:
        raw_project = result.config.raw.get("project")
        if isinstance(raw_project, dict) and raw_project.get("name"):
            return str(raw_project["name"])
    if result.config.status == ConfigLoadStatus.OK:
        return "[dim]unnamed_project[/dim]"
    if result.is_initialized and result.config.status != ConfigLoadStatus.NOT_FOUND:
        return "[dim]unknown (invalid config)[/dim]"
    return "[dim]Uninitialized[/dim]"


def format_config_status(result: WorktreeStatusResult) -> str:
    """Format config status with color-coded codes or path."""
    if result.config.status == ConfigLoadStatus.OK:
        config_rel = display_path(result.config.config_path, result.root_dir)
        return f"ok ({config_rel})"
    return CONFIG_STATUS_DISPLAY.get(
        result.config.status,
        f"[red]{result.config.status.value.upper()}[/red]",
    )


def format_git_branch(result: WorktreeStatusResult) -> str:
    """Format active git branch or non-git status badge."""
    if not result.git.is_git_repo:
        return "[yellow]NOT_A_GIT_REPO[/yellow]"
    if result.git.is_dirty:
        return f"[yellow]{result.git.branch} (dirty)[/yellow]"
    return result.git.branch


def format_agent_model(result: WorktreeStatusResult) -> str:
    """Format configured agent model or unconfigured fallback."""
    if result.config.config is not None and result.config.config.agent.model:
        return result.config.config.agent.model
    return "[dim]Not Configured[/dim]"


def format_sandboxes_status(result: WorktreeStatusResult) -> str:
    """Format active sandboxes count or N/A when config is unavailable."""
    if not result.config.is_valid:
        return "[dim]N/A[/dim]"
    return f"{result.sandboxes.active_sandboxes} / {result.sandboxes.max_active_sandboxes} max"


def format_catalog_status(result: WorktreeStatusResult) -> str:
    """Format catalog item counts or N/A when config is unavailable."""
    if not result.config.is_valid:
        return "[dim]N/A[/dim]"
    valid_items = result.catalog.total_items - result.catalog.invalid_items
    return f"{valid_items} valid / {result.catalog.total_items} total"


def build_status_table(result: WorktreeStatusResult) -> Table:
    """Build Rich Table representing workspace status summary."""
    table = Table(title=get_table_title(result), title_justify="left", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Project Name", format_project_name(result))
    table.add_row("Config Status", format_config_status(result))
    table.add_row("Active Git Branch", format_git_branch(result))
    table.add_row("Agent Model", format_agent_model(result))
    table.add_row("Active Sandboxes", format_sandboxes_status(result))
    table.add_row("Catalog Items", format_catalog_status(result))
    return table
