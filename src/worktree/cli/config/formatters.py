"""ComponentFormatters for config CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus


class ConfigLoadFormatter(ComponentFormatter[ConfigLoadResult]):
    """Formatter for configuration load and validation results."""

    def to_rich(self, data: ConfigLoadResult) -> Any:
        """Render configuration load status, not-initialized hint, or error panel."""
        if data.ok:
            return Text(f"Configuration valid at '{data.config_path}'.")

        if data.status == ConfigLoadStatus.NOT_FOUND:
            return Group(
                Text("Worktree workspace is not initialized."),
                Text("Hint: Run 'wt init' to initialize Worktree in this repository."),
            )

        message = (
            "\n\n".join(data.errors) if data.errors else f"Configuration failed to load ({data.status.value.upper()})."
        )
        return Panel(message, title="Invalid Worktree Configuration", border_style="red")

    def to_json_serializable(self, data: ConfigLoadResult) -> dict[str, Any]:
        """Convert ConfigLoadResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")


def register_config_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register config formatters on the target UiDispatcher."""
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(ConfigLoadResult, ConfigLoadFormatter())


register_config_formatters()
