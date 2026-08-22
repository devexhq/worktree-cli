"""Renderers for `wt config` subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from worktree.common.formatters import format_warning_bullets
from worktree.common.utils import RichOutput
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.serialize import as_json


def format_config_value(value: object) -> str:
    """Format parsed value for CLI output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, list, dict)):
        return json.dumps(value)
    return str(value)


def render_config_show(
    config: WorktreeConfig,
    config_path: Path,
    *,
    rich_output: RichOutput,
) -> None:
    """Print source metadata header and normalized configuration JSON."""
    payload = f"Config: {config_path.as_posix()}\nStatus: valid\n\n{as_json(config)}"
    rich_output.console.print(
        payload,
        end="",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def render_config_validate_success(
    config_path: Path,
    warnings: list[str],
    *,
    rich_output: RichOutput,
) -> None:
    """Print successful configuration validation report with optional warnings."""
    status_label = "valid with warnings" if warnings else "valid"
    lines = [
        f"Config: {config_path.as_posix()}",
        f"Status: {status_label}",
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        lines.extend(format_warning_bullets(warnings))
        lines.append("")
    lines.append("Config is valid.")
    payload = "\n".join(lines) + "\n"
    rich_output.console.print(
        payload,
        end="",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def render_config_validation_warnings(
    warnings: list[str],
    *,
    rich_output: RichOutput,
) -> None:
    """Print trailing validation warnings block."""
    warning_block = "Warnings:\n" + "\n".join(format_warning_bullets(warnings))
    rich_output.console.print(
        warning_block,
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
