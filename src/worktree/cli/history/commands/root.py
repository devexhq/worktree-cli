from pathlib import Path
from typing import Annotated

import typer

from worktree.common.utils import RichOutput
from worktree.core.db import BlueprintKind, RunStatus, WorktreeDb
from worktree.core.history import HistoryListResult, HistoryListService


def history_root_command(
    *,
    db: WorktreeDb,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
    cwd: Path | None = None,
    output: RichOutput | None = None,
) -> HistoryListResult:
    """Execute history list query and render results to console."""
    return HistoryListService(
        limit=limit,
        status=status,
        kind=kind,
        cwd=cwd,
        db=db,
        output=output or RichOutput(),
    ).execute()


def history_root(
    ctx: typer.Context,
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum number of execution runs to display (defaults to 20).",
    ),
    status: Annotated[
        RunStatus | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by run status (running, completed, failed, cancelled, paused).",
            case_sensitive=False,
        ),
    ] = None,
    kind: Annotated[
        BlueprintKind | None,
        typer.Option(
            "--kind",
            "-k",
            help="Filter by blueprint kind (task, workflow).",
            case_sensitive=False,
        ),
    ] = None,
) -> None:
    """Inspect past blueprint execution sessions, step details, and checkpoints."""
    if ctx.invoked_subcommand is not None:
        return

    db = WorktreeDb()
    outcome = history_root_command(
        limit=limit,
        status=status.value if status is not None else None,
        kind=kind.value if kind is not None else None,
        db=db,
    )
    if not outcome.ok:
        raise typer.Exit(code=1)
