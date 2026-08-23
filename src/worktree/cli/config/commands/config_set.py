"""Handles `wt config set` command."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.core.config.mutate import set_config_value_result
from worktree.core.config.parser import parse_config_value

from ..renderers import format_config_value


def config_set_command(
    key: str,
    value: str,
    *,
    context: Context,
) -> None:
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
    parsed_value = parse_config_value(value)
    result = set_config_value_result(key, parsed_value, path=context.cwd)

    if not result.ok:
        message = "\n\n".join(result.errors) if result.errors else "Failed to update configuration."
        output.error_panel("Config Error", message)
        output.print()
        raise typer.Exit(code=1)

    value_str = format_config_value(result.value)
    type_name = type(result.value).__name__
    output.success(f"Config updated: {result.key} = {value_str} ({type_name})")
    output.print()
    raise typer.Exit(code=0)
