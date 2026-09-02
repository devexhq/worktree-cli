"""Tests for ConfigLoadFormatter and UI dispatching."""

from __future__ import annotations

from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from tests.helpers import render_rich
from worktree.cli.config.formatters import ConfigLoadFormatter
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import ProjectConfig, WorktreeConfig


class ConfigLoadFormatterTests:
    """Tests for ConfigLoadFormatter."""

    def test_to_rich_ok(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="test")),
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert "Configuration valid at '/workspace/.worktree/config.json'." in rich_renderable.plain

    def test_to_rich_not_found(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Configuration file not found (CONFIG_NOT_FOUND)."],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Worktree workspace is not initialized." in rendered
        assert "Hint: Run 'wt init' to initialize Worktree in this repository." in rendered

    def test_to_rich_schema_invalid(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Schema validation failed (CONFIG_SCHEMA_INVALID): project.name is required"],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Invalid Worktree Configuration" in rendered
        assert "CONFIG_SCHEMA_INVALID" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Configuration file not found."],
        )
        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["status"] == "not_found"
        assert dumped["errors"] == ["Configuration file not found."]
