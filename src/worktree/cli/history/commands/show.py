"""Show command handler for ``wt history show``."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db import RunsDb

from ..models import HistoryShowResult, HistoryShowStatus
from ..renderers import (
    render_history_not_found,
    render_history_show,
    render_not_initialized,
)


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


def history_show_command(
    session_id: str,
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Show detailed metadata, error details, and checkpoint contents for a session.

    Args:
        session_id: Session identifier to show.
        cwd: Repository root. Defaults to process CWD.
        rich_output: Optional injected console helper for testing.
    """
    result = collect_history_show(session_id, cwd=cwd)
    if result.status is HistoryShowStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, rich_output=rich_output)
        raise typer.Exit(code=1)

    if result.status is HistoryShowStatus.NOT_FOUND or result.run is None:
        render_history_not_found(session_id, rich_output=rich_output)
        raise typer.Exit(code=1)

    render_history_show(result.run, rich_output=rich_output)
    raise typer.Exit(code=0)
