from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.db import WorktreeDb
from worktree.core.history import HistoryShowResult, HistoryShowService


def history_show_command(
    session_id: str,
    *,
    db: WorktreeDb,
    cwd: Path | None = None,
    output: RichOutput | None = None,
) -> HistoryShowResult:
    """Execute session show query and render results to console."""
    return HistoryShowService(
        session_id=session_id,
        cwd=cwd,
        db=db,
        output=output or RichOutput(),
    ).execute()


def history_show(
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
) -> None:
    """Show detailed metadata, error messages, and checkpoint state for a session."""
    db = WorktreeDb()
    outcome = history_show_command(session_id, db=db)
    if not outcome.ok:
        raise typer.Exit(code=1)
