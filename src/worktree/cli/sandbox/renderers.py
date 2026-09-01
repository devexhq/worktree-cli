"""Rich renderers for ``wt sandbox`` commands."""

from __future__ import annotations

from rich.syntax import Syntax
from rich.table import Table

from worktree.common.utils import RichOutput
from worktree.core.db import SandboxRecord
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStrategy,
    SandboxDiffResult,
    SandboxDiffStatus,
)

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


def render_sandbox_not_found(sandbox_id: str, *, output: RichOutput) -> None:
    """Render the not-found error panel for ``wt sandbox show`` / ``wt sandbox delete``."""
    message = f"Sandbox '{sandbox_id}' not found.\nFix:\n- run `wt sandbox list` to see known sandboxes"
    output.add_error_panel("Sandbox Not Found", message)


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


def render_sandbox_already_cleaned(sandbox_id: str, *, output: RichOutput) -> None:
    """Render the idempotent already-cleaned message for delete."""
    output.add_line(f"Sandbox '{sandbox_id}' is already cleaned; nothing to remove.")


def render_sandbox_delete_success(sandbox_id: str, *, output: RichOutput) -> None:
    """Render success line after a sandbox is deleted."""
    output.add_success(f"Sandbox deleted: {sandbox_id}")


def sandbox_delete_confirm_prompt(sandbox: SandboxRecord) -> str:
    """Build the confirmation prompt text for ``wt sandbox delete``."""
    return (
        f"Delete sandbox '{sandbox.id}' (branch {sandbox.branch_name}, "
        f"path {sandbox.sandbox_path})?\n"
        "This removes the git worktree and branch."
    )


def render_sandbox_apply_success(result: SandboxApplyResult, *, output: RichOutput) -> None:
    """Render success block for ``wt sandbox apply``."""
    strategy_label = result.strategy.value
    output.add_success(f"Applied sandbox {result.sandbox_id} to workspace ({strategy_label})")

    if result.strategy == SandboxApplyStrategy.SQUASH and result.commit_sha:
        output.add_dim_bullet(f"Commit: {result.commit_sha}")
    elif result.touched_files:
        files_count = len(result.touched_files)
        files_text = f"{files_count} file changed" if files_count == 1 else f"{files_count} files changed"
        output.add_dim_bullet(files_text)

    output.add_dim_bullet("Status updated: merged")

    if result.cleaned_up:
        output.add_dim_bullet("Sandbox worktree and branch deleted")

    for warning in result.warnings:
        output.add_dim_bullet(warning)


def render_sandbox_apply_failed(result: SandboxApplyResult, *, output: RichOutput) -> None:
    """Render error panel for ``wt sandbox apply`` failure."""
    message = "\n\n".join(result.errors) if result.errors else "Sandbox apply failed."
    output.add_error_panel("Sandbox Apply Failed", message)


def render_sandbox_diff(result: SandboxDiffResult, *, stat: bool, output: RichOutput) -> None:
    """Render unified diff or file stats for ``wt sandbox diff``."""
    if result.status == SandboxDiffStatus.EMPTY_DIFF:
        output.add_line(f"Sandbox '{result.sandbox_id}' has no changes compared to base commit.")
        return

    if not result.ok:
        message = "\n\n".join(result.errors) if result.errors else "Failed to generate diff."
        output.add_error_panel("Sandbox Diff Failed", message)
        return

    if stat:
        output.add_line(result.stat_text.strip())
    else:
        syntax = Syntax(result.diff_text.strip(), "diff", word_wrap=True)
        output.add_line(syntax)
