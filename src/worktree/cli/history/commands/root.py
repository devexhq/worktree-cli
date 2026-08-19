"""Root command handler for ``wt history`` (listing past executions)."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db import BlueprintKind, RunsDb, RunStatus

from ..models import HistoryListResult, HistoryListStatus
from ..renderers import render_history_list, render_not_initialized


def collect_history_list(
    limit: int | None = 20,
    status: str | None = None,
    kind: str | None = None,
    *,
    cwd: Path | None = None,
) -> HistoryListResult:
    """Load configuration and retrieve filtered execution runs from database.

    Args:
        limit: Maximum number of runs to return (defaults to 20).
        status: Optional lifecycle status filter (e.g. 'completed', 'failed').
        kind: Optional blueprint kind filter ('task', 'workflow').
        cwd: Repository root. Defaults to process CWD.

    Returns:
        Structured list result containing execution records or initialization error.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return HistoryListResult(
            status=HistoryListStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    status_filter: RunStatus | str | None = None
    if status is not None:
        try:
            status_filter = RunStatus(status.lower())
        except ValueError:
            status_filter = status

    kind_filter: BlueprintKind | str | None = None
    if kind is not None:
        try:
            kind_filter = BlueprintKind(kind.lower())
        except ValueError:
            kind_filter = kind

    db = RunsDb(root)
    runs = db.list(limit=limit, status=status_filter, kind=kind_filter)
    return HistoryListResult(status=HistoryListStatus.OK, runs=runs)


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
