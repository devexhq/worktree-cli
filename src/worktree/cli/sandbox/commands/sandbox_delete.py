"""Sandbox delete command handler."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db import (
    SandboxStatus,
)
from worktree.core.db.repositories.sandboxes import SandboxesRepository
from worktree.core.git_sandbox import GitSandboxManager, SandboxSession

from ..models import (
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
    sandbox_id: str,
    *,
    cwd: Path | None = None,
) -> SandboxDeleteResult:
    """Load config and look up one sandbox for delete (no mutation).

    Args:
        sandbox_id: Sandbox primary key to delete.
        cwd: Repository root. Defaults to process CWD.

    Returns:
        Structured delete result. Does not print, confirm, or clean up.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    row = SandboxesRepository(root).get(sandbox_id)
    if row is None:
        return SandboxDeleteResult(status=SandboxDeleteStatus.NOT_FOUND)

    if row.status is SandboxStatus.CLEANED:
        return SandboxDeleteResult(
            status=SandboxDeleteStatus.ALREADY_CLEANED,
            sandbox=row,
        )

    return SandboxDeleteResult(status=SandboxDeleteStatus.READY, sandbox=row)


def sandbox_delete_command(
    sandbox_id: str,
    force: bool = False,
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Delete a tracked sandbox worktree and branch.

    Confirms before mutating unless ``force`` is True. Already-cleaned rows are
    an idempotent no-op. Exit ``0`` on success or already-cleaned; exit ``1``
    when not initialized, not found, or confirmation is declined/EOF.

    Args:
        sandbox_id: Sandbox primary key to delete.
        force: When True, skip the confirmation prompt.
        cwd: Repository root. Defaults to process CWD.
        rich_output: Optional injected console helpers.
    """
    root = (cwd or Path.cwd()).resolve()
    output = rich_output or RichOutput()
    result = collect_sandbox_delete(sandbox_id, cwd=root)

    if result.status is SandboxDeleteStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, rich_output=output)
        raise typer.Exit(code=1)
    if result.status is SandboxDeleteStatus.NOT_FOUND:
        render_sandbox_not_found(sandbox_id, rich_output=output)
        raise typer.Exit(code=1)
    if result.status is SandboxDeleteStatus.ALREADY_CLEANED:
        render_sandbox_already_cleaned(sandbox_id, rich_output=output)
        raise typer.Exit(code=0)
    if result.sandbox is None:
        render_sandbox_not_found(sandbox_id, rich_output=output)
        raise typer.Exit(code=1)

    row = result.sandbox

    if not force:
        try:
            confirmed = typer.confirm(
                sandbox_delete_confirm_prompt(row),
                default=False,
            )
        except typer.Abort:
            confirmed = False
        if not confirmed:
            output.info("Aborted.")
            raise typer.Exit(code=1)

    session = SandboxSession(
        session_id=row.id,
        target_branch=row.branch_name,
        sandbox_path=row.sandbox_path,
        base_commit=row.base_commit,
        name=row.name,
        created_at=row.created_at,
    )
    GitSandboxManager(cwd=root).cleanup_sandbox(session)
    render_sandbox_delete_success(sandbox_id, rich_output=output)
    raise typer.Exit(code=0)
