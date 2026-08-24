"""Typer application registration for ``wt history``."""

from __future__ import annotations

from typing import Annotated

import typer

from worktree.cli.context import CliContext
from worktree.core.db import BlueprintKind, RunStatus

from .commands.root import history_root_command
from .commands.show import history_show_command

history_app = typer.Typer(
    name="history",
    help="Inspect past blueprint execution sessions, step details, and checkpoints.",
    invoke_without_command=True,
)


@history_app.callback(invoke_without_command=True)
def history_callback(
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
    if ctx.invoked_subcommand is None:
        context: CliContext = ctx.obj["context"]
        outcome = history_root_command(
            context,
            limit=limit,
            status=status.value if status is not None else None,
            kind=kind.value if kind is not None else None,
        )
        context.output.print()
        if not outcome.ok:
            raise typer.Exit(code=1)


@history_app.command("show")
def history_show(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
) -> None:
    """Show detailed metadata, error messages, and checkpoint state for a session."""
    context: CliContext = ctx.obj["context"]
    outcome = history_show_command(
        context,
        session_id,
    )
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
