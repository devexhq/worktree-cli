"""Rich renderers for ``wt sandbox`` commands."""

from __future__ import annotations

from rich.table import Table

from getworktree.common.utils import RichOutput
from getworktree.core.db import SandboxRecord

rich_output = RichOutput()


def render_not_initialized(errors: list[str]) -> None:
    """Render the not-initialized error panel for sandbox commands."""
    message = (
        "\n\n".join(errors)
        if errors
        else (
            ".worktree/config.json not found.\n"
            "Fix:\n"
            "- run `wt init` to create `.worktree/config.json`"
        )
    )
    rich_output.error_panel("Worktree Not Initialized", message)


def render_empty_list() -> None:
    """Render the empty-state line when no sandboxes match."""
    rich_output.info("No sandboxes found.")


def build_sandbox_table(sandboxes: list[SandboxRecord]) -> Table:
    """Build the ``Worktree Sandboxes`` table for list output.

    Args:
        sandboxes: Rows to render (already filtered/reconciled).

    Returns:
        A Rich table with ID, Name, Branch, Status, Created columns.
    """
    table = Table(title="Worktree Sandboxes", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Branch")
    table.add_column("Status")
    table.add_column("Created")

    for row in sandboxes:
        name = row.name if row.name is not None else "[dim]-[/dim]"
        table.add_row(
            row.id,
            name,
            row.branch_name,
            row.status.value,
            row.created_at,
        )
    return table


def render_sandbox_list(sandboxes: list[SandboxRecord]) -> None:
    """Render empty state or the sandboxes table."""
    if not sandboxes:
        render_empty_list()
        return
    rich_output.info(build_sandbox_table(sandboxes))
