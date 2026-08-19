"""Show command execution logic for ``wt history show``."""

from __future__ import annotations

import typer

from worktree.core.history import HistoryShowService


def history_show(
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
) -> None:
    """Show detailed metadata, error messages, and checkpoint state for a session."""
    outcome = HistoryShowService(session_id=session_id).execute()
    if not outcome.ok:
        raise typer.Exit(code=1)
