"""Sandbox prune command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.sandbox import GitSandboxManager

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
    result = GitSandboxManager(path=context.cwd, db=context.db.sandboxes).prune_sandboxes(
        dry_run=dry_run,
        force=force,
        runs_db=context.db.runs,
    )

    if not result.items and not result.errors:
        if output_format == "terminal":
            context.dispatcher.console.print("No stale sandboxes found.")
        return SandboxPruneCommandOutcome(result=result)

    for item in result.items:
        context.dispatcher.dispatch(item, output_format=output_format)

    if result.errors:
        for err in result.errors:
            context.dispatcher.console.print(f"[red]Error: {err}[/red]")

    return SandboxPruneCommandOutcome(
        result=result,
        errors=list(result.errors),
        warnings=list(result.warnings),
    )
