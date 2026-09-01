"""Sandbox show command handler."""

from __future__ import annotations

from pathlib import Path

from worktree.cli.context import CliContext
from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxStatus,
)

from ..models import (
    SandboxShowCommandOutcome,
    SandboxShowResult,
    SandboxShowStatus,
)


def collect_sandbox_show(
    context: CliContext,
    sandbox_id: str,
) -> SandboxShowResult:
    """Load config, look up one sandbox, and reconcile a stale active row.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to show.

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
    context: CliContext,
    sandbox_id: str,
    output_format: str = "terminal",
) -> SandboxShowCommandOutcome:
    """Show detail for one tracked sandbox.

    Read-only aside from reconciling a stale ``active`` row whose sandbox
    directory was removed out-of-band.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to show.
        output_format: Presentation format ("terminal" or "json").
    """
    result = collect_sandbox_show(context, sandbox_id)
    context.dispatcher.dispatch(result, output_format=output_format)
    if result.status is SandboxShowStatus.NOT_INITIALIZED:
        return SandboxShowCommandOutcome(errors=list(result.errors))
    if result.status is SandboxShowStatus.NOT_FOUND or result.sandbox is None:
        return SandboxShowCommandOutcome(errors=[f"Sandbox '{sandbox_id}' not found."])

    return SandboxShowCommandOutcome(sandbox=result.sandbox)
