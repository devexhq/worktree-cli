"""Collection service for sandbox deletion."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.sandbox.models import SandboxDeleteResult, SandboxDeleteStatus


def collect_sandbox_delete(
    path: Path,
    db: SandboxesRepository,
    *,
    sandbox_id: str,
) -> SandboxDeleteResult:
    """Look up one sandbox for delete (no mutation)."""
    row = db.get(sandbox_id)
    if row is None:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_FOUND,
            sandbox_id=sandbox_id,
            errors=[f"Sandbox '{sandbox_id}' not found."],
            fixes=["Run `wt sandbox list` to see known sandboxes"],
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
