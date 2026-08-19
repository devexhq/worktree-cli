"""Root command handler for ``wt history`` (listing past executions)."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput

from ..models import HistoryListStatus
from ..renderers import render_history_list, render_not_initialized
from ..services import collect_history_list


def history_root_command(
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """List blueprint execution history with optional filtering.

    Args:
        limit: Maximum number of rows to display (default: 20).
        status: Filter by run status (running, completed, failed, cancelled, paused).
        kind: Filter by blueprint kind (task, workflow).
        cwd: Repository root. Defaults to process CWD.
        rich_output: Optional injected console helper for testing.
    """
    result = collect_history_list(limit=limit, status=status, kind=kind, cwd=cwd)
    if result.status is HistoryListStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, rich_output=rich_output)
        raise typer.Exit(code=1)

    render_history_list(result.runs, rich_output=rich_output)
    raise typer.Exit(code=0)
