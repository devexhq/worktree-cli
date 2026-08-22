"""Sandbox command handlers: create, list, show, and delete tracked sandboxes."""

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

from .models import (
    SandboxDeleteResult,
    SandboxDeleteStatus,
    SandboxListResult,
    SandboxListStatus,
    SandboxShowResult,
    SandboxShowStatus,
)
from .renderers import (
    render_not_initialized,
    render_sandbox_already_cleaned,
    render_sandbox_create_failed,
    render_sandbox_create_success,
    render_sandbox_delete_success,
    render_sandbox_list,
    render_sandbox_not_found,
    render_sandbox_show,
    sandbox_delete_confirm_prompt,
)


def sandbox_create_command(
    name: str | None = None,
    base_ref: str | None = None,
    wip: bool = False,
    *,
    cwd: Path | None = None,
) -> None:
    """Create an isolated git worktree sandbox.

    Calls ``GitSandboxManager.create_sandbox_result`` and renders success or a
    classified failure panel. Exit ``0`` on success (including non-fatal
    warnings); exit ``1`` on any failed create status.

    Args:
        name: Optional human-readable sandbox name.
        base_ref: Optional git ref override for worktree creation.
        wip: When True, overlay uncommitted working-tree changes.
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    result = GitSandboxManager(cwd=root).create_sandbox_result(
        name=name,
        base_ref=base_ref,
        include_wip=wip,
    )
    if not result.ok or result.session is None:
        render_sandbox_create_failed(result.errors)
        raise typer.Exit(code=1)

    render_sandbox_create_success(
        result.session,
        warnings=result.warnings,
        cwd=root,
    )
    raise typer.Exit(code=0)


def collect_sandbox_list(
    status: str | None = None,
    *,
    cwd: Path | None = None,
) -> SandboxListResult:
    """Load config, reconcile stale active rows, and return list data.

    Args:
        status: Optional status filter (``active``, ``merged``, ``cleaned``,
            ``conflict``). Reconciliation always runs on the full row set first.
        cwd: Repository root. Defaults to process CWD.

    Returns:
        Structured list result. Does not print or exit.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return SandboxListResult(
            status=SandboxListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    db = SandboxesRepository(root)
    db.reconcile_stale_active()

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = db.list(status=status_filter)
    return SandboxListResult(status=SandboxListStatus.OK, sandboxes=rows)


def sandbox_list_command(
    status: str | None = None,
    *,
    cwd: Path | None = None,
) -> None:
    """List tracked sandboxes with lifecycle status.

    Read-only aside from reconciling stale ``active`` rows whose sandbox
    directory was removed out-of-band. Exit ``0`` on success (including empty
    lists); exit ``1`` when Worktree is not initialized.

    Args:
        status: Optional status filter validated by Typer at the CLI layer.
        cwd: Repository root. Defaults to process CWD.
    """
    result = collect_sandbox_list(status, cwd=cwd)
    if result.status is SandboxListStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)

    render_sandbox_list(result.sandboxes)
    raise typer.Exit(code=0)


def collect_sandbox_show(
    sandbox_id: str,
    *,
    cwd: Path | None = None,
) -> SandboxShowResult:
    """Load config, look up one sandbox, and reconcile a stale active row.

    Args:
        sandbox_id: Sandbox primary key to show.
        cwd: Repository root. Defaults to process CWD.

    Returns:
        Structured show result. Does not print or exit.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return SandboxShowResult(
            status=SandboxShowStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    db = SandboxesRepository(root)
    row = db.get(sandbox_id)
    if row is None:
        return SandboxShowResult(status=SandboxShowStatus.NOT_FOUND)

    reconciled_rows = db.reconcile_stale_active(sandbox_id)
    reconciled = bool(reconciled_rows)
    if reconciled:
        row = reconciled_rows[0]

    disk_present = Path(row.sandbox_path).exists()
    return SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=row,
        disk_present=disk_present,
        reconciled=reconciled,
    )


def sandbox_show_command(
    sandbox_id: str,
    *,
    cwd: Path | None = None,
) -> None:
    """Show detail for one tracked sandbox.

    Read-only aside from reconciling a stale ``active`` row whose sandbox
    directory was removed out-of-band. Exit ``0`` when found (including after
    reconciliation); exit ``1`` when not initialized or not found.

    Args:
        sandbox_id: Sandbox primary key to show.
        cwd: Repository root. Defaults to process CWD.
    """
    result = collect_sandbox_show(sandbox_id, cwd=cwd)
    if result.status is SandboxShowStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors)
        raise typer.Exit(code=1)
    if result.status is SandboxShowStatus.NOT_FOUND or result.sandbox is None:
        render_sandbox_not_found(sandbox_id)
        raise typer.Exit(code=1)

    render_sandbox_show(
        result.sandbox,
        disk_present=result.disk_present,
        reconciled=result.reconciled,
    )
    raise typer.Exit(code=0)


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
        rich_output: Optional injected console helpers (tests).
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
