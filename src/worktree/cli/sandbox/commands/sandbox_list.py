"""Sandbox list command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.sandbox import (
    Sandbox,
    SandboxListStatus,
)

from ..models import (
    SandboxListCommandOutcome,
)


def sandbox_list_command(
    context: CliContext,
    status: str | None = None,
    output_format: str = "terminal",
) -> SandboxListCommandOutcome:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band.

    Args:
        context: CLI context instance.
        status: Optional status filter validated by Typer at the CLI layer.
        output_format: Presentation format ("terminal" or "json").
    """
    result = Sandbox(path=context.cwd, db=context.db.sandboxes).list(status=status)
    ui_dispatcher.dispatch(result, output_format=output_format)
    if result.status is SandboxListStatus.NOT_INITIALIZED:
        return SandboxListCommandOutcome(errors=list(result.errors))

    return SandboxListCommandOutcome(sandboxes=result.sandboxes)
