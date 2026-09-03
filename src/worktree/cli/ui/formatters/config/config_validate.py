"""ComponentFormatter for ConfigValidationResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel, render_list_fixes
from worktree.common.formatters import format_warning_bullets
from worktree.common.types import ComponentFormatter
from worktree.core.config.validate import ConfigValidationResult


def _format_valid_config(data: ConfigValidationResult) -> Text:
    """Format successful configuration validation output with optional warnings and fixes."""
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
    if fixes_msg := render_list_fixes(data.fixes):
        lines.append(fixes_msg)
        lines.append("")
    lines.append("Config is valid.")
    return Text("\n".join(lines))


def _format_invalid_config(data: ConfigValidationResult) -> Any:
    """Format failed configuration validation error panel and warnings."""
    panel = build_error_panel(
        "Config Validation Failed",
        data.errors,
        "Configuration validation failed.",
        data.fixes,
    )
    if data.warnings:
        warning_block = "Warnings:\n" + "\n".join(format_warning_bullets(data.warnings))
        return Group(panel, Text(warning_block))
    return panel


class ConfigValidateFormatter(ComponentFormatter[ConfigValidationResult]):
    """Formatter for configuration validation results."""

    def to_rich(self, data: ConfigValidationResult) -> Any:
        """Render status label, warning bullets, or error panel."""
        if data.ok:
            return _format_valid_config(data)
        return _format_invalid_config(data)

    def to_json_serializable(self, data: ConfigValidationResult) -> dict[str, Any]:
        """Convert ConfigValidationResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
