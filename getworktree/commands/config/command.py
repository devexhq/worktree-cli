"""Handles `wt config` subcommands."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.common.utils import RichOutput
from getworktree.core.config.loader import load_config_result
from getworktree.core.config.serialize import as_json

rich_output = RichOutput()


def config_show_command(*, cwd: Path | None = None) -> None:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

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

    # Header + blank line + plain JSON (no Rich markup/highlight/wrap).
    payload = (
        f"Config: {result.config_path.as_posix()}\n"
        f"Status: valid\n"
        f"\n"
        f"{as_json(result.config)}"
    )
    rich_output.console.print(
        payload,
        end="",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
