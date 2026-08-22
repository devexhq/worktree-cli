"""Handles `wt config` subcommands."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.config.mutate import set_config_value_result
from worktree.core.config.parser import parse_config_value
from worktree.core.config.validate import validate_config_result

from ..renderers import (
    format_config_value,
    render_config_show,
    render_config_validate_success,
    render_config_validation_warnings,
)

_DEFAULT_RICH_OUTPUT = RichOutput()


def config_set_command(
    key: str,
    value: str,
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Set a configuration value by top-level or nested dot-path key.

    String inputs are parsed into native types (bool, int, float, list, dict).
    Missing intermediate objects are created. Type collisions, schema key errors,
    and load/write failures abort without partial writes. Validates keys and values
    against the V1 schema allow-list.

    Args:
        key: Dot-path key (e.g. ``agent.model`` or ``version``).
        value: String value from CLI to parse and store at ``key``.
        cwd: Repository root for config resolution. Defaults to process CWD.
        rich_output: Optional RichOutput presenter.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()
    parsed_value = parse_config_value(value)
    result = set_config_value_result(key, parsed_value, cwd=root)

    if not result.ok:
        message = "\n\n".join(result.errors) if result.errors else "Failed to update configuration."
        output.error_panel("Config Error", message)
        raise typer.Exit(code=1)

    value_str = format_config_value(result.value)
    type_name = type(result.value).__name__
    output.success(f"Config updated: {result.key} = {value_str} ({type_name})")
    raise typer.Exit(code=0)


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


def config_validate_command(
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Validate config and print the CLI validation report.

    Calls ``validate_config_result`` only. Success paths print a plain text
    report and exit 0 (warnings allowed). Failure paths print a Rich error
    panel titled ``Config Validation Failed`` and exit 1. Read-only: never
    creates, repairs, or mutates config files.

    Args:
        cwd: Repository root for config resolution. Defaults to process CWD.
        rich_output: Optional RichOutput presenter.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    root = (cwd or Path.cwd()).resolve()
    result = validate_config_result(cwd=root)

    if result.ok:
        render_config_validate_success(result.config_path, list(result.warnings), rich_output=output)
        raise typer.Exit(code=0)

    message = "\n\n".join(result.errors) if result.errors else "Configuration validation failed."
    output.error_panel("Config Validation Failed", message)

    if result.warnings:
        render_config_validation_warnings(list(result.warnings), rich_output=output)

    raise typer.Exit(code=1)
