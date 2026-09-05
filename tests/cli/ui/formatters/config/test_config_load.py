"""Tier 2 presentation contract tests for ConfigLoadFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.config.config_load import ConfigLoadFormatter
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import ProjectConfig, WorktreeConfig


class ConfigLoadFormatterTests:
    """Tests for ConfigLoadFormatter."""

    def test_to_rich_valid_config_renders_path_and_name(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="test")),
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "/workspace/.worktree/config.json" in rendered
        assert "test" in rendered

    def test_to_rich_not_found_renders_error_code(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Configuration file not found at '/workspace/.worktree/config.json' (CONFIG_NOT_FOUND)."],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_NOT_FOUND" in rendered

    def test_to_rich_schema_invalid_renders_fix(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Schema validation failed (CONFIG_SCHEMA_INVALID): project.name is required"],
            fixes=["Run `wt config validate` for details"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_SCHEMA_INVALID" in rendered
        assert "Run `wt config validate` for details" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Configuration file not found."],
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "not_found",
            "config_path": "/workspace/.worktree/config.json",
            "raw": None,
            "config": None,
            "errors": ["Configuration file not found."],
            "warnings": [],
            "fixes": [],
        }
