"""Sandbox apply command handler."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.sandbox import GitSandboxManager, SandboxApplyStrategy

from ..models import SandboxApplyCommandOutcome
from ..renderers import render_sandbox_apply_failed, render_sandbox_apply_success


def sandbox_apply_command(
    context: CliContext,
    sandbox_id: str,
    *,
    strategy: SandboxApplyStrategy = SandboxApplyStrategy.PATCH,
    allow_dirty: bool = False,
    dry_run: bool = False,
    delete: bool = False,
    message: str | None = None,
) -> SandboxApplyCommandOutcome:
    """Apply sandbox changes back to main workspace.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to apply.
        strategy: Apply strategy ('patch' or 'squash').
        allow_dirty: Allow application even if main repository is dirty.
        dry_run: Perform conflict check without mutating workspace.
        delete: Clean up sandbox upon successful application.
        message: Optional commit message for squash strategy.
    """
    manager = GitSandboxManager(path=context.cwd, db=context.db.sandboxes)
    result = manager.apply_sandbox(
        sandbox_id=sandbox_id,
        strategy=strategy,
        allow_dirty=allow_dirty,
        dry_run=dry_run,
        delete=delete,
        message=message,
    )

    if not result.ok:
        render_sandbox_apply_failed(result, output=context.output)
        return SandboxApplyCommandOutcome(
            result=result,
            errors=list(result.errors),
            warnings=list(result.warnings),
        )

    render_sandbox_apply_success(result, output=context.output)
    return SandboxApplyCommandOutcome(result=result, warnings=list(result.warnings))
