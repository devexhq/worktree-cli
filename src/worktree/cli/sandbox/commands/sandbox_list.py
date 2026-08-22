"""Sandbox list command handler."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.core.config.loader import load_config_result
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
    cwd: Path | None = None,
    db: WorktreeDb | None = None,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        status: Optional status filter (``active``, ``merged``, ``cleaned``,
            ``conflict``). Reconciliation always runs on the full row set first.
        cwd: Repository root. Defaults to process CWD.
        db: Optional WorktreeDb instance.

    Returns:
        Structured list result. Does not print or exit.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return SandboxListResult(
            status=SandboxListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    db = db or WorktreeDb(root)
    _reconcile_stale_active_sandboxes(db=db)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = db.sandboxes.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)


def sandbox_list_command(
    status: str | None = None,
    *,
    cwd: Path | None = None,
    db: WorktreeDb | None = None,
) -> None:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band. Exit ``0`` on success (including empty
    lists); exit ``1`` when Worktree is not initialized.

    Args:
        status: Optional status filter validated by Typer at the CLI layer.
        cwd: Repository root. Defaults to process CWD.
        db: Optional WorktreeDb instance.
    """
    db = db or WorktreeDb(cwd)
    result = collect_sandbox_list(status, cwd=cwd, db=db)
    if result.status is SandboxListStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)

    render_sandbox_list(result.sandboxes)
    raise typer.Exit(code=0)
