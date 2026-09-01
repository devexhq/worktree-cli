"""Sandbox diff command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import default_dispatcher
from worktree.core.sandbox import GitSandboxManager

from ..models import SandboxDiffCommandOutcome


def sandbox_diff_command(
    context: CliContext,
    sandbox_id: str,
    *,
    stat: bool = False,
    output_format: str = "terminal",
) -> SandboxDiffCommandOutcome:
    """Inspect unified diff or file summary statistics for a sandbox.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to diff.
        stat: When True, show diffstat summary instead of full unified diff.
        output_format: Presentation format ("terminal" or "json").
    """
    manager = GitSandboxManager(path=context.cwd, db=context.db.sandboxes)
    result = manager.diff_sandbox(sandbox_id, stat=stat)

    default_dispatcher.dispatch(result, output_format=output_format)
    return SandboxDiffCommandOutcome(
        result=result,
        errors=list(result.errors),
        warnings=list(result.warnings),
    )
