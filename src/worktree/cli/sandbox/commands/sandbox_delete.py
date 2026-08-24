"""Sandbox delete command handler."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxStatus,
)
from worktree.core.git_sandbox import GitSandboxManager, SandboxSession

from ..models import (
    SandboxDeleteCommandOutcome,
    SandboxDeleteResult,
    SandboxDeleteStatus,
)
from ..renderers import (
    render_not_initialized,
    render_sandbox_already_cleaned,
    render_sandbox_delete_success,
    render_sandbox_not_found,
    sandbox_delete_confirm_prompt,
)


def collect_sandbox_delete(
    context: CliContext,
    sandbox_id: str,
) -> SandboxDeleteResult:
    """Load config and look up one sandbox for delete (no mutation).

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to delete.

    Returns:
        Structured delete result. Does not print, confirm, or clean up.
    """
    load = load_config_result(path=context.cwd)
    if not load.ok:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    row = context.db.sandboxes.get(sandbox_id)
    if row is None:
        return SandboxDeleteResult(status=SandboxDeleteStatus.NOT_FOUND)

    if row.status is SandboxStatus.CLEANED:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.ALREADY_CLEANED,
            sandbox=row,
        )

    return SandboxDeleteResult(status=SandboxDeleteStatus.READY, sandbox=row)


def _confirm_or_abort(row: object, output: RichOutput) -> bool:
    """Prompt user for confirmation; return True if confirmed."""
    try:
        confirmed = typer.confirm(
            sandbox_delete_confirm_prompt(row),  # pyright: ignore[reportArgumentType]
            default=False,
        )
    except typer.Abort:
        confirmed = False
    if not confirmed:
        output.add_line("Aborted.")
    return confirmed


def sandbox_delete_command(
    context: CliContext,
    sandbox_id: str,
    force: bool = False,
) -> SandboxDeleteCommandOutcome:
    """Delete a tracked sandbox worktree and branch.

    Confirms before mutating unless ``force`` is True. Already-cleaned rows are
    an idempotent no-op.

    Args:
        context: CLI context instance.
        sandbox_id: Sandbox primary key to delete.
        force: When True, skip the confirmation prompt.
    """
    output = context.output
    result = collect_sandbox_delete(context, sandbox_id)

    if result.status is SandboxDeleteStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, output=output)
        return SandboxDeleteCommandOutcome(errors=list(result.errors))
    if result.status is SandboxDeleteStatus.NOT_FOUND:
        render_sandbox_not_found(sandbox_id, output=output)
        return SandboxDeleteCommandOutcome(errors=[f"Sandbox '{sandbox_id}' not found."])
    if result.status is SandboxDeleteStatus.ALREADY_CLEANED:
        render_sandbox_already_cleaned(sandbox_id, output=output)
        return SandboxDeleteCommandOutcome(already_cleaned=True)
    if result.sandbox is None:
        render_sandbox_not_found(sandbox_id, output=output)
        return SandboxDeleteCommandOutcome(errors=[f"Sandbox '{sandbox_id}' not found."])

    row = result.sandbox

    if not force and not _confirm_or_abort(row, output):
        return SandboxDeleteCommandOutcome(errors=["Aborted."])

    session = SandboxSession(
        session_id=row.id,
        target_branch=row.branch_name,
        sandbox_path=row.sandbox_path,
        base_commit=row.base_commit,
        name=row.name,
        created_at=row.created_at,
    )
    GitSandboxManager(path=context.cwd, db=context.db.sandboxes).cleanup_sandbox(session)
    render_sandbox_delete_success(sandbox_id, output=output)
    return SandboxDeleteCommandOutcome(deleted=True)
