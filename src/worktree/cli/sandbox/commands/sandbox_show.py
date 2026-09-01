"""Sandbox show command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.sandbox import (
    Sandbox,
    SandboxShowStatus,
)

from ..models import (
    SandboxShowCommandOutcome,
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
    result = Sandbox(path=context.cwd, db=context.db.sandboxes).show(sandbox_id)
    ui_dispatcher.dispatch(result, output_format=output_format)
    if result.status is SandboxShowStatus.NOT_INITIALIZED:
        return SandboxShowCommandOutcome(errors=list(result.errors))
    if result.status is SandboxShowStatus.NOT_FOUND or result.sandbox is None:
        return SandboxShowCommandOutcome(errors=[f"Sandbox '{sandbox_id}' not found."])

    return SandboxShowCommandOutcome(sandbox=result.sandbox)
