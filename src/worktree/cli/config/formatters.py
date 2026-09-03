"""ComponentFormatters for config CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.config.renderers import format_config_value
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.formatters import format_warning_bullets
from worktree.common.types import ComponentFormatter
from worktree.core.config.loader import (
    ConfigLoadResult,
    resolve_config_path,
)
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.mutate import ConfigSetResult
from worktree.core.config.serialize import as_json
from worktree.core.config.validate import ConfigValidationResult


class ConfigLoadFormatter(ComponentFormatter[ConfigLoadResult]):
    """Formatter for configuration load and validation results."""

    def to_rich(self, data: ConfigLoadResult) -> Any:
        """Render configuration source path header and normalized JSON body, or error panel."""
        if data.ok and data.config is not None:
            payload = f"Config: {data.config_path.as_posix()}\nStatus: valid\n\n{as_json(data.config)}"
            return Text(payload)

        message = (
            "\n\n".join(data.errors) if data.errors else f"Configuration failed to load ({data.status.value.upper()})."
        )
        return Panel(message, title="Config Error", border_style="red")

    def to_json_serializable(self, data: ConfigLoadResult) -> dict[str, Any]:
        """Convert ConfigLoadResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class ConfigShowFormatter(ComponentFormatter[WorktreeConfig]):
    """Formatter for effective Worktree configuration."""

    def to_rich(self, data: WorktreeConfig) -> Any:
        """Render config source path header and normalized JSON block.

        Args:
            data: Loaded, validated Worktree configuration.

        Returns:
            Rich Text renderable containing path header and JSON body.
        """
        config_path = resolve_config_path()
        payload = f"Config: {config_path.as_posix()}\nStatus: valid\n\n{as_json(data)}"
        return Text(payload)

    def to_json_serializable(self, data: WorktreeConfig) -> dict[str, Any]:
        """Convert WorktreeConfig to primitive dictionary for JSON serialization.

        Args:
            data: Loaded, validated Worktree configuration.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class ConfigValidateFormatter(ComponentFormatter[ConfigValidationResult]):
    """Formatter for configuration validation results."""

    def to_rich(self, data: ConfigValidationResult) -> Any:
        """Render status label, warning bullets, or error panel.

        Args:
            data: Structured result of configuration validation.

        Returns:
            Rich renderable object (Text, Panel, or Group).
        """
        if data.ok:
            status_label = "valid with warnings" if data.warnings else "valid"
            lines = [
                f"Config: {data.config_path.as_posix()}",
                f"Status: {status_label}",
                "",
            ]
            if data.warnings:
                lines.append("Warnings:")
                lines.extend(format_warning_bullets(data.warnings))
                lines.append("")
            lines.append("Config is valid.")
            return Text("\n".join(lines))

        message = "\n\n".join(data.errors) if data.errors else "Configuration validation failed."
        panel = Panel(message, title="Config Validation Failed", border_style="red")
        if data.warnings:
            warning_block = "Warnings:\n" + "\n".join(format_warning_bullets(data.warnings))
            return Group(panel, Text(warning_block))
        return panel

    def to_json_serializable(self, data: ConfigValidationResult) -> dict[str, Any]:
        """Convert ConfigValidationResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of configuration validation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class ConfigSetFormatter(ComponentFormatter[ConfigSetResult]):
    """Formatter for configuration mutation results."""

    def to_rich(self, data: ConfigSetResult) -> Any:
        """Render configuration update confirmation or error panel.

        Args:
            data: Structured result of config set operation.

        Returns:
            Rich Text or Panel renderable.
        """
        if data.ok:
            value_str = format_config_value(data.value)
            type_name = type(data.value).__name__
            return Text.from_markup(
                f"[bold green]✔  Config updated: {data.key} = {value_str} ({type_name})[/bold green]"
            )

        message = "\n\n".join(data.errors) if data.errors else "Failed to update configuration."
        return Panel(message, title="Config Error", border_style="red")

    def to_json_serializable(self, data: ConfigSetResult) -> dict[str, Any]:
        """Convert ConfigSetResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of config set operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_config_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register config formatters on the target UiDispatcher."""
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(ConfigLoadResult, ConfigLoadFormatter())
    target.register(WorktreeConfig, ConfigShowFormatter())
    target.register(ConfigValidationResult, ConfigValidateFormatter())
    target.register(ConfigSetResult, ConfigSetFormatter())


register_config_formatters()
