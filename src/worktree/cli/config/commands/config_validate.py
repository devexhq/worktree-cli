"""Handles `wt config validate` command."""

from worktree.cli.context import CliContext
from worktree.core.config import Config

from ..models import ConfigValidateCommandOutcome
from ..renderers import (
    render_config_validate_success,
    render_config_validation_warnings,
)


def config_validate_command(
    context: CliContext,
) -> ConfigValidateCommandOutcome:
    """Validate config and print the CLI validation report.

    Calls ``validate_config_result`` only. Success paths print a plain text
    report (warnings allowed). Failure paths print a Rich error
    panel titled ``Config Validation Failed``. Read-only: never
    creates, repairs, or mutates config files.

    Args:
        context: CLI context instance.
    """
    output = context.output
    result = Config(context.cwd).validate()

    if result.ok:
        render_config_validate_success(result.config_path, list(result.warnings), output=output)
        return ConfigValidateCommandOutcome(config_path=result.config_path, warnings=list(result.warnings))

    message = "\n\n".join(result.errors) if result.errors else "Configuration validation failed."
    output.add_error_panel("Config Validation Failed", message)

    if result.warnings:
        render_config_validation_warnings(list(result.warnings), output=output)

    return ConfigValidateCommandOutcome(
        config_path=result.config_path,
        warnings=list(result.warnings),
        errors=list(result.errors) if result.errors else [message],
    )
