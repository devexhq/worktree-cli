"""Typer application registration for ``wt run``."""

import typer

from .commands.root import run_root


def register_run_command(app: typer.Typer) -> None:
    """Register the top-level ``run`` command on the root Typer application."""
    app.command(
        name="run",
        help="Execute any blueprint by name (task or workflow).",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(run_root)
