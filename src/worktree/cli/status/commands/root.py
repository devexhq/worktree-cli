"""Status command implementation."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.context import load_context

from ..renderers import render_status_table

_DEFAULT_RICH_OUTPUT = RichOutput()


def status_command(*, cwd: Path | None = None, rich_output: RichOutput | None = None) -> None:
    """Inspect active worktree configuration and repository context."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()

    try:
        ctx = load_context(root)
    except Exception as exc:
        output.error_panel("Context Error", str(exc))
        raise typer.Exit(code=1) from exc

    render_status_table(ctx, rich_output=output)
