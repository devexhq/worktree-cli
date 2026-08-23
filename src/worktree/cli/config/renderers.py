"""Renderers for `wt config` subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text

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
    output: RichOutput,
) -> None:
    """Buffer source metadata header and normalized configuration JSON without markup."""
    payload = f"Config: {config_path.as_posix()}\nStatus: valid\n\n{as_json(config)}"
    output.info(Text(payload))


def render_config_validate_success(
    config_path: Path,
    warnings: list[str],
    *,
    output: RichOutput,
) -> None:
    """Buffer successful configuration validation report with optional warnings without markup."""
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
    payload = "\n".join(lines)
    output.info(Text(payload))


def render_config_validation_warnings(
    warnings: list[str],
    *,
    output: RichOutput,
) -> None:
    """Buffer trailing validation warnings block without markup."""
    warning_block = "Warnings:\n" + "\n".join(format_warning_bullets(warnings))
    output.info(Text(warning_block))
