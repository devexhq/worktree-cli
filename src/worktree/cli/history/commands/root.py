"""Root command execution logic for ``wt history``."""

from __future__ import annotations

from typing import Annotated

import typer

from worktree.cli.history.services import HistoryListService
from worktree.core.db import BlueprintKind, RunStatus


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

    outcome = HistoryListService(
        limit=limit,
        status=status.value if status is not None else None,
        kind=kind.value if kind is not None else None,
    ).execute()
    if not outcome.ok:
        raise typer.Exit(code=1)
