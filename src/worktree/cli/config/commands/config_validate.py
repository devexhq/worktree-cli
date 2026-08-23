"""Handles `wt config validate` command."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.common.utils import RichOutput
from worktree.core.config.validate import validate_config_result

from ..renderers import (
    render_config_validate_success,
    render_config_validation_warnings,
)

_DEFAULT_RICH_OUTPUT = RichOutput()


def config_validate_command(
    *,
    context: Context,
    rich_output: RichOutput | None = None,
) -> None:
    """Validate config and print the CLI validation report.

    Calls ``validate_config_result`` only. Success paths print a plain text
    report and exit 0 (warnings allowed). Failure paths print a Rich error
    panel titled ``Config Validation Failed`` and exit 1. Read-only: never
    creates, repairs, or mutates config files.

    Args:
        context: CLI context instance.
        rich_output: Optional RichOutput presenter.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    result = validate_config_result(path=context.cwd)

    if result.ok:
        render_config_validate_success(result.config_path, list(result.warnings), rich_output=output)
        raise typer.Exit(code=0)

    message = "\n\n".join(result.errors) if result.errors else "Configuration validation failed."
    output.error_panel("Config Validation Failed", message)

    if result.warnings:
        render_config_validation_warnings(list(result.warnings), rich_output=output)

    raise typer.Exit(code=1)
