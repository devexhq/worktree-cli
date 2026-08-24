"""Root command execution logic for ``wt run``."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.core.engine import BlueprintRunService


def run_root(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Blueprint name to run (task or workflow)."),
    no_sandbox: bool = typer.Option(
        False,
        "--no-sandbox",
        help="Run execution in-place in the working tree without creating a Git sandbox.",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        help="Retain sandbox worktree after execution.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Override default target agent adapter.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Explicit session identifier.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable interactive prompts; prompt_user failures abort the run.",
    ),
) -> None:
    """Execute a task or workflow blueprint."""
    context: CliContext = ctx.obj["context"]
    outcome = BlueprintRunService(
        name=name,
        path=context.cwd,
        runs_db=context.db.runs,
        catalog_db=context.db.catalog,
        output=context.output,
        kind=None,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=list(ctx.args),
        non_interactive=non_interactive,
    ).execute()
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
