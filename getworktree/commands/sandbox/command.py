"""Sandbox command handlers: create, list, and show tracked worktree sandboxes."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.commands.sandbox.models import (
    SandboxListResult,
    SandboxListStatus,
    SandboxShowResult,
    SandboxShowStatus,
)
from getworktree.commands.sandbox.renderers import (
    render_not_initialized,
    render_sandbox_create_failed,
    render_sandbox_create_success,
    render_sandbox_list,
    render_sandbox_not_found,
    render_sandbox_show,
)
from getworktree.core.config.loader import load_config_result
from getworktree.core.db import (
    SandboxStatus,
    get_sandbox,
    list_sandboxes,
    update_sandbox_status,
)
from getworktree.core.git_sandbox import GitSandboxManager


def _reconcile_stale_active_sandboxes(*, cwd: Path) -> None:
    """Mark active rows whose sandbox directory is gone as cleaned."""
    for row in list_sandboxes(cwd=cwd):
        if row.status is not SandboxStatus.ACTIVE:
            continue
        if Path(row.sandbox_path).is_dir():
            continue
        update_sandbox_status(row.id, SandboxStatus.CLEANED, cwd=cwd)


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

    _reconcile_stale_active_sandboxes(cwd=root)

    status_filter: SandboxStatus | None = None
    if status is not None:
        status_filter = SandboxStatus(status)

    rows = list_sandboxes(status=status_filter, cwd=root)
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

    row = get_sandbox(sandbox_id, cwd=root)
    if row is None:
        return SandboxShowResult(status=SandboxShowStatus.NOT_FOUND)

    reconciled = False
    if row.status is SandboxStatus.ACTIVE and not Path(row.sandbox_path).is_dir():
        updated = update_sandbox_status(row.id, SandboxStatus.CLEANED, cwd=root)
        if updated is not None:
            row = updated
        else:
            row = row.model_copy(update={"status": SandboxStatus.CLEANED})
        reconciled = True

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
    if result.status is SandboxShowStatus.NOT_FOUND:
        render_sandbox_not_found(sandbox_id)
        raise typer.Exit(code=1)

    assert result.sandbox is not None
    render_sandbox_show(
        result.sandbox,
        disk_present=result.disk_present,
        reconciled=result.reconciled,
    )
    raise typer.Exit(code=0)
