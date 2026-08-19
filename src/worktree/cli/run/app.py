"""Typer application command definition for ``wt run``."""

import typer

from .commands.root import root_command


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
):
    """Execute a task or workflow blueprint."""
    outcome = root_command(
        name=name,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=list(ctx.args),
        non_interactive=non_interactive,
    )
    if not outcome.ok:
        raise typer.Exit(code=1)


def register_run_command(app: typer.Typer) -> None:
    """Register the top-level ``run`` command on the root Typer application."""
    app.command(
        name="run",
        help="Execute any blueprint by name (task or workflow).",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(run_root)
