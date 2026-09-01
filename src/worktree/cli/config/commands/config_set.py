"""Handles `wt config set` command."""

from worktree.cli.context import CliContext
from worktree.core.config import Config

from ..models import ConfigSetCommandOutcome
from ..renderers import format_config_value


def config_set_command(
    context: CliContext,
    key: str,
    value: str,
) -> ConfigSetCommandOutcome:
    """Set a configuration value by top-level or nested dot-path key.

    String inputs are parsed into native types (bool, int, float, list, dict).
    Missing intermediate objects are created. Type collisions, schema key errors,
    and load/write failures abort without partial writes. Validates keys and values
    against the V1 schema allow-list.

    Args:
        key: Dot-path key (e.g. ``agent.model`` or ``version``).
        value: String value from CLI to parse and store at ``key``.
        context: CLI context instance.
    """
    output = context.output
    result = Config(context.cwd).set(key, value)

    if not result.ok:
        message = "\n\n".join(result.errors) if result.errors else "Failed to update configuration."
        output.add_error_panel("Config Error", message)
        return ConfigSetCommandOutcome(errors=list(result.errors))

    value_str = format_config_value(result.value)
    type_name = type(result.value).__name__
    output.add_success(f"Config updated: {result.key} = {value_str} ({type_name})")
    return ConfigSetCommandOutcome(key=result.key, value=result.value)
