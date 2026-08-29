"""Typer application registration for ``wt diff`` (Controller: context extraction & exit handling)."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext

from .commands.root import diff_command


def register_diff_command(app: typer.Typer) -> None:
    """Register the top-level ``diff`` command on the root Typer application."""

    @app.command(
        name="diff",
        help="View syntax-highlighted unified diff for an execution session.",
    )
    def diff_root(
        ctx: typer.Context,
        session_id: str | None = typer.Argument(
            None,
            help="Session identifier (e.g. sbx_a1b2c3d4). If omitted, displays the latest session diff.",
        ),
        raw: bool = typer.Option(
            False,
            "--raw",
            help="Output unformatted plain text diff directly to stdout.",
        ),
    ) -> None:
        """View syntax-highlighted unified diff for a session."""
        context: CliContext = ctx.obj["context"]
        outcome = diff_command(context, session_id=session_id, raw=raw)
        context.output.print()
        if not outcome.ok:
            raise typer.Exit(code=1)
