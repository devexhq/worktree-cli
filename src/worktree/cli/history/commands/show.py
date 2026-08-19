"""Show command handler for ``wt history show``."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput

from ..models import HistoryShowStatus
from ..renderers import (
    render_history_not_found,
    render_history_show,
    render_not_initialized,
)
from ..services import collect_history_show


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
