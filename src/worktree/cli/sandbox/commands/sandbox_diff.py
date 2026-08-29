"""Sandbox diff command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.git_sandbox import GitSandboxManager

from ..models import SandboxDiffCommandOutcome
from ..renderers import render_sandbox_diff


def sandbox_diff_command(
    context: CliContext,
    sandbox_id: str,
    *,
    stat: bool = False,
) -> SandboxDiffCommandOutcome:
    """Inspect unified diff or file summary statistics for a sandbox.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to diff.
        stat: When True, show diffstat summary instead of full unified diff.
    """
    manager = GitSandboxManager(path=context.cwd, db=context.db.sandboxes)
    result = manager.diff_sandbox_result(sandbox_id, stat=stat)

    render_sandbox_diff(result, stat=stat, output=context.output)
    return SandboxDiffCommandOutcome(
        result=result,
        errors=list(result.errors),
        warnings=list(result.warnings),
    )
