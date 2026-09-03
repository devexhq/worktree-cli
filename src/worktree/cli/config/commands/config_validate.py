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

    Calls ``validate_config_result`` only. Success paths print a plain text
    report (warnings allowed). Failure paths print a Rich error
    panel titled ``Config Validation Failed``. Read-only: never
    creates, repairs, or mutates config files.

    Args:
        context: CLI context instance.
        output_format: Presentation format ("terminal" or "json").
    """
    result = Config(path=context.cwd).validate()
    ui_dispatcher.dispatch(result, output_format=output_format)

    if result.ok:
        return ConfigValidateCommandOutcome(config_path=result.config_path, warnings=list(result.warnings))

    message = "\n\n".join(result.errors) if result.errors else "Configuration validation failed."
    return ConfigValidateCommandOutcome(
        config_path=result.config_path,
        warnings=list(result.warnings),
        errors=list(result.errors) if result.errors else [message],
    )
