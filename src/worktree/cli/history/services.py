"""Query and collection services for history CLI commands."""

from __future__ import annotations

from pathlib import Path

from worktree.core.config.loader import load_config_result
from worktree.core.db import BlueprintKind, RunsDb, RunStatus

from .models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)


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


def collect_history_show(
    session_id: str,
    *,
    cwd: Path | None = None,
) -> HistoryShowResult:
    """Look up execution session metadata, errors, and checkpoint contents from database.

    Args:
        session_id: Session identifier to inspect.
        cwd: Repository root. Defaults to process CWD.

    Returns:
        Structured show result containing execution record or classified error.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok:
        return HistoryShowResult(
            status=HistoryShowStatus.NOT_INITIALIZED,
            errors=list(load.errors),
        )

    db = RunsDb(root)
    row = db.get(session_id)
    if row is None:
        return HistoryShowResult(status=HistoryShowStatus.NOT_FOUND)

    return HistoryShowResult(status=HistoryShowStatus.OK, run=row)
