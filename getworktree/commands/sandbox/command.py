"""Sandbox command handlers: list tracked worktree sandboxes."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.commands.sandbox.models import SandboxListResult, SandboxListStatus
from getworktree.commands.sandbox.renderers import (
    render_not_initialized,
    render_sandbox_list,
)
from getworktree.core.config.loader import load_config_result
from getworktree.core.db import SandboxStatus, list_sandboxes, update_sandbox_status


def _reconcile_stale_active_sandboxes(*, cwd: Path) -> None:
    """Mark active rows whose sandbox directory is gone as cleaned."""
    for row in list_sandboxes(cwd=cwd):
        if row.status is not SandboxStatus.ACTIVE:
            continue
        if Path(row.sandbox_path).is_dir():
            continue
        update_sandbox_status(row.id, SandboxStatus.CLEANED, cwd=cwd)


def collect_sandbox_list(
    status: str | None = None,
    *,
    cwd: Path | None = None,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        status: Optional status filter (``active``, ``merged``, ``cleaned``,
            ``conflict``). Reconciliation always runs on the full row set first.
        cwd: Repository root. Defaults to process CWD.

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

    _reconcile_stale_active_sandboxes(cwd=root)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = list_sandboxes(status=status_filter, cwd=root)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)


def sandbox_list_command(
    status: str | None = None,
    *,
    cwd: Path | None = None,
) -> None:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band. Exit ``0`` on success (including empty
    lists); exit ``1`` when Worktree is not initialized.

    Args:
        status: Optional status filter validated by Typer at the CLI layer.
        cwd: Repository root. Defaults to process CWD.
    """
    result = collect_sandbox_list(status, cwd=cwd)
    if not result.ok:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)

    render_sandbox_list(result.sandboxes)
    raise typer.Exit(code=0)
