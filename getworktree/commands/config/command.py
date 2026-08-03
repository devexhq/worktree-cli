"""Handles `wt config` subcommands."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.common.utils import RichOutput
from getworktree.core.config.loader import load_config_result
from getworktree.core.config.serialize import as_json
from getworktree.core.config.validate import validate_config_result

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


def config_validate_command(*, cwd: Path | None = None) -> None:
    """Validate config and print the CLI validation report.

    Calls ``validate_config_result`` only. Success paths print a plain text
    report and exit 0 (warnings allowed). Failure paths print a Rich error
    panel titled ``Config Validation Failed`` and exit 1. Read-only: never
    creates, repairs, or mutates config files.

    Args:
        cwd: Repository root for config resolution. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    result = validate_config_result(cwd=root)

    if result.ok:
        status_label = "valid with warnings" if result.warnings else "valid"
        lines = [
            f"Config: {result.config_path.as_posix()}",
            f"Status: {status_label}",
            "",
        ]
        if result.warnings:
            lines.append("Warnings:")
            lines.extend(_format_warning_bullets(result.warnings))
            lines.append("")
        lines.append("Config is valid.")
        payload = "\n".join(lines) + "\n"
        rich_output.console.print(
            payload,
            end="",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        raise typer.Exit(code=0)

    message = (
        "\n\n".join(result.errors)
        if result.errors
        else "Configuration validation failed."
    )
    rich_output.error_panel("Config Validation Failed", message)

    if result.warnings:
        warning_block = "Warnings:\n" + "\n".join(
            _format_warning_bullets(result.warnings)
        )
        rich_output.console.print(
            warning_block,
            markup=False,
            highlight=False,
            soft_wrap=True,
        )

    raise typer.Exit(code=1)


def _format_warning_bullets(warnings: list[str]) -> list[str]:
    """Format engine warnings as bullet lines with indented continuations."""
    lines: list[str] = []
    for warning in warnings:
        parts = warning.splitlines() or [""]
        lines.append(f"- {parts[0]}")
        for continuation in parts[1:]:
            lines.append(f"  {continuation}")
    return lines
