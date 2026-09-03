"""Handles `wt config show` command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.config import Config

from ..models import ConfigShowCommandOutcome


def config_show_command(
    context: CliContext,
    output_format: str = "terminal",
) -> ConfigShowCommandOutcome:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

    Args:
        context: CLI context instance.
        output_format: Presentation format ("terminal" or "json").
    """
    output = context.output
    result = Config(path=context.cwd).load()

    if not result.ok or result.config is None:
        message = "\n\n".join(result.errors) if result.errors else "Failed to load configuration."
        output.add_error_panel("Config Error", message)
        return ConfigShowCommandOutcome(errors=list(result.errors))

    ui_dispatcher.dispatch(result.config, output_format=output_format)
    return ConfigShowCommandOutcome(config=result.config, config_path=result.config_path)
