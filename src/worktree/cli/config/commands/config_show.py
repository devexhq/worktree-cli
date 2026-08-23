"""Handles `wt config show` command."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.core.config.loader import load_config_result

from ..renderers import render_config_show


def config_show_command(
    *,
    context: Context,
) -> None:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

    Args:
        context: CLI context instance.
    """
    output = context.output
    result = load_config_result(path=context.cwd)

    if not result.ok or result.config is None:
        message = "\n\n".join(result.errors) if result.errors else "Failed to load configuration."
        output.error_panel("Config Error", message)
        output.print()
        raise typer.Exit(code=1)

    render_config_show(result.config, result.config_path, output=output)
    output.print()
