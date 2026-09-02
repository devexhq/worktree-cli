"""Sandbox listing service."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import (
    SandboxesRepository,
    SandboxStatus,
)
from worktree.core.sandbox.models import (
    SandboxListResult,
    SandboxListStatus,
)


def collect_sandbox_list(
    path: Path,
    db: SandboxesRepository,
    status: str | None = None,
) -> SandboxListResult:
    """Reconcile stale active rows and return list data.

    Args:
        path: Repository root directory.
        db: SandboxesRepository instance.
        status: Optional status filter (active, merged, cleaned,
            conflict). Reconciliation always runs on the full row set first.

    Returns:
        Structured list result. Does not print or exit.
    """
    db.reconcile_stale_active()

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = db.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)
