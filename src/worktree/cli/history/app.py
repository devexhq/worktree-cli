"""Typer application registration for ``wt history``."""

from __future__ import annotations

import typer

from .commands.root import history_root
from .commands.show import history_show

history_app = typer.Typer(
    name="history",
    help="Inspect past blueprint execution sessions, step details, and checkpoints.",
    invoke_without_command=True,
)

history_app.callback(invoke_without_command=True)(history_root)
history_app.command(
    name="show",
    help="Show detailed metadata, error messages, and checkpoint state for a session.",
)(history_show)
