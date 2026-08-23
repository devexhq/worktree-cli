"""Handles `wt config show` command."""

from __future__ import annotations

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.config.models import CliContext

from ..renderers import render_config_show

_DEFAULT_RICH_OUTPUT = RichOutput()


def config_show_command(
    *,
    cli_ctx: CliContext,
    rich_output: RichOutput | None = None,
) -> None:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

    Args:
        cli_ctx: CLI context instance.
        rich_output: Optional RichOutput presenter.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    result = load_config_result(cwd=cli_ctx.cwd)

    if not result.ok or result.config is None:
        message = "\n\n".join(result.errors) if result.errors else "Failed to load configuration."
        output.error_panel("Config Error", message)
        raise typer.Exit(code=1)

    render_config_show(result.config, result.config_path, rich_output=output)
