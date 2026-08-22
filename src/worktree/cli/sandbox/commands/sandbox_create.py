"""Sandbox create command handler."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.core.git_sandbox import GitSandboxManager

from ..renderers import (
    render_sandbox_create_failed,
    render_sandbox_create_success,
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
