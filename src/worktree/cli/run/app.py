"""Typer application registration for ``wt run``."""

from __future__ import annotations

from typing import Any

import typer
from typer.core import TyperGroup

from worktree.cli.context import CliContext

from .commands.root import run_command
from .formatters import register_run_formatters

register_run_formatters()


class RunTyperGroup(TyperGroup):
    """Custom TyperGroup allowing extra args forwarding when invoked without subcommands."""

    def invoke(self, ctx: Any) -> Any:
        """Forward protected args to ctx.args when no subcommands are registered."""
        if not self.commands and self.invoke_without_command:
            ctx.args = [*getattr(ctx, "_protected_args", []), *ctx.args]
            ctx._protected_args = []
            with ctx:
                return super(TyperGroup, self).invoke(ctx)
        return super().invoke(ctx)


run_app = typer.Typer(
    cls=RunTyperGroup,
    name="run",
    help="Execute any blueprint by name (task or workflow).",
    invoke_without_command=True,
    context_settings={
        "allow_interspersed_args": True,
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
)


@run_app.callback(invoke_without_command=True)
def run_callback(
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
    auto_apply: bool = typer.Option(
        False,
        "--auto-apply",
        help="Automatically apply sandbox changes to the main workspace on successful completion.",
    ),
    format: str = typer.Option(
        "terminal",
        "--format",
        "-f",
        help="Output format: 'terminal' or 'json'.",
    ),
) -> None:
    """Execute a task or workflow blueprint."""
    context: CliContext = ctx.obj["context"]
    result = run_command(
        context,
        name=name,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        non_interactive=non_interactive,
        auto_apply=auto_apply,
        cli_args=list(ctx.args),
        output_format=format,
    )
    if not result.ok:
        raise typer.Exit(code=1)
