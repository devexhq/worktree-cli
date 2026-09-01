"""Rendering helpers for `wt status` command."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import RichOutput, display_path
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

REMEDIATION_MAP: dict[ConfigLoadStatus, str] = {
    ConfigLoadStatus.NOT_FOUND: "Run 'wt init' to initialize Worktree in this repository.",
    ConfigLoadStatus.MALFORMED_JSON: "Repair JSON syntax in .worktree/config.json or restore from backup.",
    ConfigLoadStatus.SCHEMA_INVALID: (
        "Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys."
    ),
    ConfigLoadStatus.ROOT_NOT_OBJECT: "Ensure .worktree/config.json contains a JSON object root.",
    ConfigLoadStatus.PATH_IS_DIRECTORY: "Remove directory at .worktree/config.json and run 'wt init'.",
    ConfigLoadStatus.UNREADABLE: "Check file permissions for .worktree/config.json.",
}


def _get_table_title(result: WorktreeStatusResult) -> str:
    """Determine the status table title based on workspace initialization and health."""
    if not result.is_initialized or result.config.status == ConfigLoadStatus.NOT_FOUND:
        return "Worktree Workspace Status (Uninitialized)"
    if not result.ok:
        return "Worktree Workspace Status (Degraded)"
    return "Worktree Workspace Status"


def _format_project_name(result: WorktreeStatusResult) -> str:
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


def _format_config_status(result: WorktreeStatusResult) -> str:
    """Format config status with color-coded codes or path."""
    if result.config.status == ConfigLoadStatus.OK:
        config_rel = display_path(result.config.config_path, result.root_dir)
        return f"ok ({config_rel})"
    return CONFIG_STATUS_DISPLAY.get(
        result.config.status,
        f"[red]{result.config.status.value.upper()}[/red]",
    )


def _format_git_branch(result: WorktreeStatusResult) -> str:
    """Format active git branch or non-git status badge."""
    if not result.git.is_git_repo:
        return "[yellow]NOT_A_GIT_REPO[/yellow]"
    if result.git.is_dirty:
        return f"[yellow]{result.git.branch} (dirty)[/yellow]"
    return result.git.branch


def _format_agent_model(result: WorktreeStatusResult) -> str:
    """Format configured agent model or unconfigured fallback."""
    if result.config.config is not None and result.config.config.agent.model:
        return result.config.config.agent.model
    return "[dim]Not Configured[/dim]"


def _format_sandboxes_status(result: WorktreeStatusResult) -> str:
    """Format active sandboxes count or N/A when config is unavailable."""
    if not result.config.is_valid:
        return "[dim]N/A[/dim]"
    return f"{result.sandboxes.active_sandboxes} / {result.sandboxes.max_active_sandboxes} max"


def _format_catalog_status(result: WorktreeStatusResult) -> str:
    """Format catalog item counts or N/A when config is unavailable."""
    if not result.config.is_valid:
        return "[dim]N/A[/dim]"
    valid_items = result.catalog.total_items - result.catalog.invalid_items
    return f"{valid_items} valid / {result.catalog.total_items} total"


def _collect_remediations(result: WorktreeStatusResult) -> list[str]:
    """Aggregate actionable remediation command hints for diagnosed failure modes."""
    remediations: list[str] = []
    if result.config.status in REMEDIATION_MAP:
        remediations.append(REMEDIATION_MAP[result.config.status])
    if not result.git.is_git_repo:
        remediations.append("Run 'git init' or navigate to a Git repository.")
    return remediations


def _clean_error_message(err: str) -> str:
    """Extract a concise single-line warning message from a raw error string."""
    first_line = err.split("\n")[0].strip()
    if "at '" not in first_line:
        return first_line
    prefix, _, rest = first_line.partition("at '")
    _, _, message = rest.partition("': ")
    return f"{prefix.strip()}: {message.strip()}" if message else first_line


def _collect_all_warnings(result: WorktreeStatusResult) -> list[str]:
    """Aggregate collected warnings along with sanitized config error details."""
    warnings = list(result.warnings)
    if result.config.status in (ConfigLoadStatus.OK, ConfigLoadStatus.NOT_FOUND):
        return warnings

    for err in result.config.errors:
        clean_msg = _clean_error_message(err)
        if clean_msg and clean_msg not in warnings:
            warnings.append(clean_msg)
    return warnings


def build_status_table(result: WorktreeStatusResult) -> Table:
    """Build Rich Table representing workspace status summary.

    Args:
        result: Unified workspace status collection result.

    Returns:
        A Rich table with Property and Value columns.
    """
    table = Table(title=_get_table_title(result), title_justify="left", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Project Name", _format_project_name(result))
    table.add_row("Config Status", _format_config_status(result))
    table.add_row("Active Git Branch", _format_git_branch(result))
    table.add_row("Agent Model", _format_agent_model(result))
    table.add_row("Active Sandboxes", _format_sandboxes_status(result))
    table.add_row("Catalog Items", _format_catalog_status(result))
    return table


def render_status_summary(
    result: WorktreeStatusResult,
    *,
    output: RichOutput,
) -> None:
    """Render Rich terminal summary for WorktreeStatusResult."""
    table = build_status_table(result)
    output.add_line(table)

    warnings = _collect_all_warnings(result)
    if warnings:
        output.add_spacer()
        output.add_line("[yellow]⚠️ Configuration & Context Warnings:[/yellow]")
        for warning in warnings:
            output.add_dim_bullet(warning)

    remediations = _collect_remediations(result)
    if remediations:
        output.add_spacer()
        output.add_line("Next Steps & Remediation:")
        for remediation in remediations:
            output.add_dim_bullet(remediation)
