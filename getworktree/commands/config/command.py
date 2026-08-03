"""Handles `wt config` subcommands."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.common.utils import RichOutput
from getworktree.core.config.loader import load_config_result
from getworktree.core.config.serialize import as_json

rich_output = RichOutput()


def config_show_command(*, cwd: Path | None = None) -> None:
    """Print the full normalized effective configuration as pretty JSON.

    Args:
        cwd: Repository root for config resolution. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    result = load_config_result(cwd=root)

    if not result.ok or result.config is None:
        message = (
            "\n\n".join(result.errors)
            if result.errors
            else "Failed to load configuration."
        )
        rich_output.error_panel("Config Error", message)
        raise typer.Exit(code=1)

    text = as_json(result.config)
    # Plain JSON body: no Rich markup/highlight so captures stay parseable.
    rich_output.console.print(text, end="", markup=False, highlight=False)
