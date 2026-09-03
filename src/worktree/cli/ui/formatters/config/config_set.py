"""ComponentFormatter for ConfigSetResult."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.text import Text

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

        parts: list[str] = []
        if data.errors:
            parts.append("\n\n".join(data.errors))
        else:
            parts.append("Failed to update configuration.")
        if data.fixes:
            parts.append("Fix:\n" + "\n".join(f"- {fix}" for fix in data.fixes))
        message = "\n".join(parts)
        return Panel(message, title="Config Error", border_style="red")

    def to_json_serializable(self, data: ConfigSetResult) -> dict[str, Any]:
        """Convert ConfigSetResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
