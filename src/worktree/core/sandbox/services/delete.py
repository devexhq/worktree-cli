"""Collection service for sandbox deletion."""

from __future__ import annotations

from pathlib import Path

from worktree.core.config.loader import load_config_result
from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.sandbox.models import SandboxDeleteResult, SandboxDeleteStatus


def collect_sandbox_delete(
    path: Path,
    db: SandboxesRepository,
    *,
    sandbox_id: str,
) -> SandboxDeleteResult:
    """Load config and look up one sandbox for delete (no mutation)."""
    load = load_config_result(path=path)
    if not load.ok:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_INITIALIZED,
            sandbox_id=sandbox_id,
            errors=list(load.errors),
        )

    row = db.get(sandbox_id)
    if row is None:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_FOUND,
            sandbox_id=sandbox_id,
        )

    if row.status is SandboxStatus.CLEANED:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.ALREADY_CLEANED,
            sandbox_id=sandbox_id,
            sandbox=row,
        )

    return SandboxDeleteResult(
        status=SandboxDeleteStatus.READY,
        sandbox_id=sandbox_id,
        sandbox=row,
    )
