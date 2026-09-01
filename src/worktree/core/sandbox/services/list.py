"""Sandbox listing service."""

from __future__ import annotations

from pathlib import Path

from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxesRepository,
    SandboxStatus,
)
from worktree.core.sandbox.models import (
    SandboxListResult,
    SandboxListStatus,
)


def _reconcile_stale_active_sandboxes(*, db: SandboxesRepository) -> None:
    """Mark active rows whose sandbox directory is gone as cleaned."""
    for row in db.list():
        if row.status is not SandboxStatus.ACTIVE:
            continue
        if Path(row.sandbox_path).is_dir():
            continue
        db.update_status(row.id, SandboxStatus.CLEANED)


def collect_sandbox_list(
    path: Path,
    db: SandboxesRepository,
    status: str | None = None,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        path: Repository root directory.
        db: SandboxesRepository instance.
        status: Optional status filter (active, merged, cleaned,
            conflict). Reconciliation always runs on the full row set first.

    Returns:
        Structured list result. Does not print or exit.
    """
    load = load_config_result(path=path)
    if not load.ok:
        return SandboxListResult(
            status=SandboxListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    _reconcile_stale_active_sandboxes(db=db)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = db.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)
