"""ComponentFormatter for ConfigSetResult."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.cli.ui.formatters.config.common import format_config_value
from worktree.common.types import ComponentFormatter
from worktree.core.config.mutate import ConfigSetResult


class ConfigSetFormatter(ComponentFormatter[ConfigSetResult]):
    """Formatter for configuration mutation results."""

    def to_rich(self, data: ConfigSetResult) -> Any:
        """Render configuration update confirmation or error panel."""
        if data.ok:
            value_str = format_config_value(data.value)
            type_name = type(data.value).__name__
            return Text.from_markup(
                f"[bold green]✔  Config updated: {data.key} = {value_str} ({type_name})[/bold green]"
            )

        return build_error_panel(
            "Config Error",
            data.errors,
            "Failed to update configuration.",
            data.fixes,
        )

    def to_json_serializable(self, data: ConfigSetResult) -> dict[str, Any]:
        """Convert ConfigSetResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
