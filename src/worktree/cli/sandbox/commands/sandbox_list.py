"""Sandbox list command handler."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.core.config.loader import load_config_result
from worktree.core.config.models import CliContext
from worktree.core.db import (
    SandboxStatus,
    WorktreeDb,
)

from ..models import (
    SandboxListResult,
    SandboxListStatus,
)
from ..renderers import (
    render_not_initialized,
    render_sandbox_list,
)


def _reconcile_stale_active_sandboxes(*, db: WorktreeDb) -> None:
    """Mark active rows whose sandbox directory is gone as cleaned."""
    for row in db.sandboxes.list():
        if row.status is not SandboxStatus.ACTIVE:
            continue
        if Path(row.sandbox_path).is_dir():
            continue
        db.sandboxes.update_status(row.id, SandboxStatus.CLEANED)


def collect_sandbox_list(
    status: str | None = None,
    *,
    cli_ctx: CliContext,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        status: Optional status filter (``active``, ``merged``, ``cleaned``,
            ``conflict``). Reconciliation always runs on the full row set first.
        cli_ctx: CLI context instance.

    Returns:
        Structured list result. Does not print or exit.
    """
    load = load_config_result(cwd=cli_ctx.cwd)
    if not load.ok:
        return SandboxListResult(
            status=SandboxListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    _reconcile_stale_active_sandboxes(db=cli_ctx.db)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = cli_ctx.db.sandboxes.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)


def sandbox_list_command(
    status: str | None = None,
    *,
    cli_ctx: CliContext,
) -> None:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band. Exit ``0`` on success (including empty
    lists); exit ``1`` when Worktree is not initialized.

    Args:
        status: Optional status filter validated by Typer at the CLI layer.
        cli_ctx: CLI context instance.
    """
    result = collect_sandbox_list(status, cli_ctx=cli_ctx)
    if result.status is SandboxListStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)

    render_sandbox_list(result.sandboxes)
    raise typer.Exit(code=0)
