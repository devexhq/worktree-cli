"""Rich renderers for ``wt sandbox`` commands."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from worktree.common.utils import RichOutput, display_path
from worktree.core.db import SandboxRecord
from worktree.core.git_sandbox import SandboxSession

_SANDBOX_SHOW_FIELDS = (
    "ID",
    "Name",
    "Branch",
    "Base Commit",
    "Path",
    "Status",
    "Disk",
    "Created",
    "Updated",
)


def render_not_initialized(errors: list[str], *, output: RichOutput) -> None:
    """Render the not-initialized error panel for sandbox commands."""
    output.render_not_initialized(
        errors,
        fix_hint="run `wt init` to create `.worktree/config.json`",
    )


def render_sandbox_create_failed(errors: list[str], *, output: RichOutput) -> None:
    """Render the create-failed error panel for ``wt sandbox create``."""
    message = "\n\n".join(errors) if errors else "Sandbox creation failed."
    output.error_panel("Sandbox Create Failed", message)


def render_sandbox_create_success(
    session: SandboxSession,
    *,
    output: RichOutput,
    warnings: list[str] | None = None,
    cwd: Path | None = None,
) -> None:
    """Render success block and optional non-fatal warnings for create."""
    root = (cwd or Path.cwd()).resolve()
    path_label = display_path(session.sandbox_path, root)
    output.success(f"Sandbox created: {session.session_id}")
    output.info(f"   Branch: {session.target_branch}")
    output.info(f"   Path: {path_label}")
    for warning in warnings or []:
        output.dim_bullet(warning)


def render_sandbox_not_found(sandbox_id: str, *, output: RichOutput) -> None:
    """Render the not-found error panel for ``wt sandbox show``."""
    message = f"Sandbox '{sandbox_id}' not found.\nFix:\n- run `wt sandbox list` to see known sandboxes"
    output.error_panel("Sandbox Not Found", message)


def render_empty_list(*, output: RichOutput) -> None:
    """Render the empty-state line when no sandboxes match."""
    output.info("No sandboxes found.")


def build_sandbox_table(sandboxes: list[SandboxRecord]) -> Table:
    """Build the ``Worktree Sandboxes`` table for list output.

    Args:
        sandboxes: Rows to render (already filtered/reconciled).

    Returns:
        A Rich table with ID, Name, Branch, Status, Created columns.
    """
    table = Table(title="Worktree Sandboxes", title_justify="left", show_header=True)
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


def render_sandbox_list(sandboxes: list[SandboxRecord], *, output: RichOutput) -> None:
    """Render empty state or the sandboxes table."""
    if not sandboxes:
        render_empty_list(output=output)
        return
    output.info(build_sandbox_table(sandboxes))


def build_sandbox_detail_table(sandbox: SandboxRecord, *, disk_present: bool) -> Table:
    """Build the key/value detail table for ``wt sandbox show``.

    Args:
        sandbox: Row to render (already reconciled when needed).
        disk_present: Whether ``sandbox_path`` exists on disk at render time.

    Returns:
        A two-column Rich table with fixed field order.
    """
    name = sandbox.name if sandbox.name is not None else "-"
    disk = "present" if disk_present else "missing"
    values = {
        "ID": sandbox.id,
        "Name": name,
        "Branch": sandbox.branch_name,
        "Base Commit": sandbox.base_commit,
        "Path": str(sandbox.sandbox_path),
        "Status": sandbox.status.value,
        "Disk": disk,
        "Created": sandbox.created_at,
        "Updated": sandbox.updated_at,
    }

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="bold")
    table.add_column()
    for field in _SANDBOX_SHOW_FIELDS:
        table.add_row(f"{field}:", values[field])
    return table


def render_sandbox_show(
    sandbox: SandboxRecord,
    *,
    disk_present: bool,
    reconciled: bool = False,
    output: RichOutput,
) -> None:
    """Render sandbox detail fields and an optional reconciliation note."""
    name = sandbox.name if sandbox.name is not None else "-"
    disk = "present" if disk_present else "missing"
    values = {
        "ID": sandbox.id,
        "Name": name,
        "Branch": sandbox.branch_name,
        "Base Commit": sandbox.base_commit,
        "Path": str(sandbox.sandbox_path),
        "Status": sandbox.status.value,
        "Disk": disk,
        "Created": sandbox.created_at,
        "Updated": sandbox.updated_at,
    }
    output.add_kv_table([(f"{field}", values[field]) for field in _SANDBOX_SHOW_FIELDS])
    if reconciled:
        output.info("Note: sandbox directory is missing; status updated to 'cleaned'.")


def render_sandbox_already_cleaned(sandbox_id: str, *, output: RichOutput) -> None:
    """Render the idempotent already-cleaned message for delete."""
    output.info(f"Sandbox '{sandbox_id}' is already cleaned; nothing to remove.")


def render_sandbox_delete_success(sandbox_id: str, *, output: RichOutput) -> None:
    """Render success line after a sandbox is deleted."""
    output.success(f"Sandbox deleted: {sandbox_id}")


def sandbox_delete_confirm_prompt(sandbox: SandboxRecord) -> str:
    """Build the confirmation prompt text for ``wt sandbox delete``."""
    return (
        f"Delete sandbox '{sandbox.id}' (branch {sandbox.branch_name}, "
        f"path {sandbox.sandbox_path})?\n"
        "This removes the git worktree and branch."
    )
