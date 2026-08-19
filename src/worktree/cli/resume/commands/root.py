"""Root command execution logic for ``wt resume``."""

from __future__ import annotations

import typer

from worktree.cli.blueprint import BlueprintResumeService


def resume_root(
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
    outcome = BlueprintResumeService(
        session_id=session_id,
        non_interactive=non_interactive,
    ).execute()
    if not outcome.ok:
        raise typer.Exit(code=1)
