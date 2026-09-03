"""Handles `wt config set` command."""

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.config import Config

from ..models import ConfigSetCommandOutcome


def config_set_command(
    context: CliContext,
    key: str,
    value: str,
    output_format: str = "terminal",
) -> ConfigSetCommandOutcome:
    """Set a configuration value by top-level or nested dot-path key.

    String inputs are parsed into native types (bool, int, float, list, dict).
    Missing intermediate objects are created. Type collisions, schema key errors,
    and load/write failures abort without partial writes. Validates keys and values
    against the V1 schema allow-list.

    Args:
        context: CLI context instance.
        key: Dot-path key (e.g. ``agent.model`` or ``version``).
        value: String value from CLI to parse and store at ``key``.
        output_format: Presentation format ("terminal" or "json").
    """
    result = Config(path=context.cwd).set(key, value)
    ui_dispatcher.dispatch(result, output_format=output_format)

    if not result.ok:
        return ConfigSetCommandOutcome(errors=list(result.errors))

    return ConfigSetCommandOutcome(key=result.key, value=result.value)
