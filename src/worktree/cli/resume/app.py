"""Typer application registration for ``wt resume``."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.cli.run.formatters import register_run_formatters
from worktree.cli.ui.dispatcher import ui_dispatcher

from .commands.root import resume_command

register_run_formatters()

resume_app = typer.Typer(
    name="resume",
    help="Resume a paused blueprint execution session (task or workflow).",
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": True},
)


@resume_app.callback(invoke_without_command=True)
def resume_callback(
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
    """Resume a paused blueprint execution session (task or workflow)."""
    context: CliContext = ctx.obj["context"]
    outcome = resume_command(
        context,
        session_id=session_id,
        non_interactive=non_interactive,
    )
    ui_dispatcher.dispatch(outcome)
    if not outcome.ok:
        raise typer.Exit(code=1)
