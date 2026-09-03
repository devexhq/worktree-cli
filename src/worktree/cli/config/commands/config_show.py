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

    Args:
        context: CLI context instance.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        ConfigShowCommandOutcome containing loaded config and errors.
    """
    result = Config(path=context.cwd).load()
    ui_dispatcher.dispatch(result, output_format=output_format)
    return ConfigShowCommandOutcome(
        config=result.config,
        config_path=result.config_path,
        errors=list(result.errors),
    )
