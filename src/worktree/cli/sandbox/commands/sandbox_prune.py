"""Sandbox prune command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.sandbox import Sandbox

from ..models import (
    SandboxPruneCommandOutcome,
)


def sandbox_prune_command(
    context: CliContext,
    *,
    dry_run: bool = False,
    force: bool = False,
    output_format: str = "terminal",
) -> SandboxPruneCommandOutcome:
    """Safely prune stale sandboxes, orphaned directories, and temporary branches.

    Args:
        context: CLI context instance.
        dry_run: When True, preview actions without mutating filesystem or DB.
        force: When True, delete dirty orphaned directories containing uncommitted files.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        Structured prune outcome.
    """
    result = Sandbox(
        path=context.cwd,
        db=context.db.sandboxes,
        runs_db=context.db.runs,
    ).prune(
        dry_run=dry_run,
        force=force,
    )

    ui_dispatcher.dispatch(result, output_format=output_format)

    return SandboxPruneCommandOutcome(
        result=result,
        errors=list(result.errors),
        warnings=list(result.warnings),
    )
