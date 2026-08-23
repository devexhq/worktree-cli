"""Handles `wt config show` command."""

from worktree.cli.context import Context
from worktree.core.config.loader import load_config_result

from ..models import ConfigShowCommandOutcome
from ..renderers import render_config_show


def config_show_command(
    *,
    context: Context,
) -> ConfigShowCommandOutcome:
    """Print source metadata, then the effective configuration as pretty JSON.

    Success stdout is a fixed header, a blank line, then ``as_json`` body.
    Failure paths print an error panel only (no header, no partial JSON).

    Args:
        context: CLI context instance.
    """
    output = context.output
    result = load_config_result(path=context.cwd)

    if not result.ok or result.config is None:
        message = "\n\n".join(result.errors) if result.errors else "Failed to load configuration."
        output.error_panel("Config Error", message)
        return ConfigShowCommandOutcome(ok=False, errors=list(result.errors))

    render_config_show(result.config, result.config_path, output=output)
    return ConfigShowCommandOutcome(ok=True, config=result.config, config_path=result.config_path)
