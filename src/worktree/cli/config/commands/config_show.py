"""Handles `wt config show` command."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result

from ..renderers import render_config_show

_DEFAULT_RICH_OUTPUT = RichOutput()


def config_show_command(
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

    Args:
        cwd: Repository root for config resolution. Defaults to process CWD.
        rich_output: Optional RichOutput presenter.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()
    result = load_config_result(cwd=root)

    if not result.ok or result.config is None:
        message = "\n\n".join(result.errors) if result.errors else "Failed to load configuration."
        output.error_panel("Config Error", message)
        raise typer.Exit(code=1)

    render_config_show(result.config, result.config_path, rich_output=output)
