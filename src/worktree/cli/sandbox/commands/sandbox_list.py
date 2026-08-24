"""Sandbox list command handler."""

from __future__ import annotations

from pathlib import Path

from worktree.cli.context import CliContext
from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxesRepository,
    SandboxStatus,
)

from ..models import (
    SandboxListCommandOutcome,
    SandboxListResult,
    SandboxListStatus,
)
from ..renderers import (
    render_not_initialized,
    render_sandbox_list,
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
    context: CliContext,
    status: str | None = None,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        context: CLI context instance.
        status: Optional status filter (``active``, ``merged``, ``cleaned``,
            ``conflict``). Reconciliation always runs on the full row set first.

    Returns:
        Structured list result. Does not print or exit.
    """
    load = load_config_result(path=context.cwd)
    if not load.ok:
        return SandboxListResult(
            status=SandboxListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    _reconcile_stale_active_sandboxes(db=context.db.sandboxes)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = context.db.sandboxes.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)


def sandbox_list_command(
    context: CliContext,
    status: str | None = None,
) -> SandboxListCommandOutcome:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band.

    Args:
        context: CLI context instance.
        status: Optional status filter validated by Typer at the CLI layer.
    """
    result = collect_sandbox_list(context, status)
    if result.status is SandboxListStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, output=context.output)
        return SandboxListCommandOutcome(errors=list(result.errors))

    render_sandbox_list(result.sandboxes, output=context.output)
    return SandboxListCommandOutcome(sandboxes=result.sandboxes)
