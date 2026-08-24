"""Root command execution logic for ``wt resume``."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.core.engine import BlueprintResumeService


def resume_root(
    ctx: typer.Context,
    session_id: str | None = typer.Argument(
        None,
        help="Session identifier to resume. If omitted, the latest paused session is resumed.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable interactive prompts; prompt_user failures abort the run.",
    ),
) -> None:
    """Resume a paused task or workflow blueprint execution session."""
    context: CliContext = ctx.obj["context"]
    outcome = BlueprintResumeService(
        path=context.cwd,
        db=context.db.runs,
        catalog_db=context.db.catalog,
        output=context.output,
        session_id=session_id,
        non_interactive=non_interactive,
    ).execute()
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
