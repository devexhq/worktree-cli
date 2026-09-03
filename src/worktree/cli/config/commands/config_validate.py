"""Handles `wt config validate` command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.config import Config

from ..models import ConfigValidateCommandOutcome


def config_validate_command(
    context: CliContext,
    output_format: str = "terminal",
) -> ConfigValidateCommandOutcome:
    """Validate config and print the CLI validation report.

    Args:
        context: CLI context instance.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        ConfigValidateCommandOutcome containing validation results and errors.
    """
    result = Config(path=context.cwd).validate()
    ui_dispatcher.dispatch(result, output_format=output_format)
    return ConfigValidateCommandOutcome(
        result=result,
        config_path=result.config_path,
        warnings=list(result.warnings),
        errors=list(result.errors),
    )
