"""Typer application registration for ``wt resume``."""

import typer

from .commands.root import resume_root


def register_resume_command(app: typer.Typer) -> None:
    """Register the top-level ``resume`` command on the root Typer application."""
    app.command(
        name="resume",
        help="Resume a paused blueprint execution session (task or workflow).",
    )(resume_root)
