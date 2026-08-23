"""Sandbox show command handler."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.cli.context import Context
from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxStatus,
)

from ..models import (
    SandboxShowResult,
    SandboxShowStatus,
)
from ..renderers import (
    render_not_initialized,
    render_sandbox_not_found,
    render_sandbox_show,
)


def collect_sandbox_show(
    sandbox_id: str,
    *,
    context: Context,
) -> SandboxShowResult:
    """Load config, look up one sandbox, and reconcile a stale active row.

    Args:
        sandbox_id: Sandbox primary key to show.
        context: CLI context instance.

    Returns:
        Structured show result. Does not print or exit.
    """
    load = load_config_result(path=context.cwd)
    if not load.ok:
        return SandboxShowResult(
            status=SandboxShowStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    row = context.db.sandboxes.get(sandbox_id)
    if row is None:
        return SandboxShowResult(status=SandboxShowStatus.NOT_FOUND)

    reconciled = False
    if row.status is SandboxStatus.ACTIVE and not Path(row.sandbox_path).is_dir():
        updated = context.db.sandboxes.update_status(row.id, SandboxStatus.CLEANED)
        if updated is not None:
            row = updated
        else:
            row = row.model_copy(update={"status": SandboxStatus.CLEANED})
        reconciled = True

    disk_present = Path(row.sandbox_path).exists()
    return SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=row,
        disk_present=disk_present,
        reconciled=reconciled,
    )


def sandbox_show_command(
    sandbox_id: str,
    *,
    context: Context,
) -> None:
    """Show detail for one tracked sandbox.

    Read-only aside from reconciling a stale ``active`` row whose sandbox
    directory was removed out-of-band. Exit ``0`` when found (including after
    reconciliation); exit ``1`` when not initialized or not found.

    Args:
        sandbox_id: Sandbox primary key to show.
        context: CLI context instance.
    """
    result = collect_sandbox_show(sandbox_id, context=context)
    if result.status is SandboxShowStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)
    if result.status is SandboxShowStatus.NOT_FOUND or result.sandbox is None:
        render_sandbox_not_found(sandbox_id)
        raise typer.Exit(code=1)

    render_sandbox_show(
        result.sandbox,
        disk_present=result.disk_present,
        reconciled=result.reconciled,
    )
    raise typer.Exit(code=0)
