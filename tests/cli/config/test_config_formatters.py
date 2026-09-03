"""Tests for config ComponentFormatters and UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from tests.helpers import render_rich
from worktree.cli.config.formatters import (
    ConfigLoadFormatter,
    ConfigSetFormatter,
    ConfigShowFormatter,
    ConfigValidateFormatter,
    register_config_formatters,
)
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import AgentConfig, ProjectConfig, WorktreeConfig
from worktree.core.config.mutate import ConfigSetResult, ConfigSetStatus
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)


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
        rendered = rich_renderable.plain
        assert "Config: /workspace/.worktree/config.json" in rendered
        assert "Status: valid" in rendered
        assert "test" in rendered

    def test_to_rich_not_found(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["Configuration file not found at '/workspace/.worktree/config.json' (CONFIG_NOT_FOUND)."],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Config Error" in rendered
        assert "CONFIG_NOT_FOUND" in rendered

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
        assert "Config Error" in rendered
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


class ConfigShowFormatterTests:
    """Tests for ConfigShowFormatter."""

    def test_to_rich(self) -> None:
        formatter = ConfigShowFormatter()
        config = WorktreeConfig(
            version=1,
            project=ProjectConfig(name="test-show-app"),
            agent=AgentConfig(model="gemini-2.5-pro"),
        )
        rich_renderable = formatter.to_rich(config)
        assert isinstance(rich_renderable, Text)
        rendered = rich_renderable.plain
        assert "Config:" in rendered
        assert "Status: valid" in rendered
        assert "test-show-app" in rendered
        assert "gemini-2.5-pro" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = ConfigShowFormatter()
        config = WorktreeConfig(
            version=1,
            project=ProjectConfig(name="test-show-app"),
            agent=AgentConfig(model="gemini-2.5-pro"),
        )
        dumped = formatter.to_json_serializable(config)
        assert isinstance(dumped, dict)
        assert dumped["version"] == 1
        assert dumped["project"]["name"] == "test-show-app"
        assert dumped["agent"]["model"] == "gemini-2.5-pro"
        assert dumped["paths"]["root_dir"] == ".worktree"


class ConfigValidateFormatterTests:
    """Tests for ConfigValidateFormatter."""

    def test_to_rich_valid(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=[],
            errors=[],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        rendered = rich_renderable.plain
        assert "Config: /workspace/.worktree/config.json" in rendered
        assert "Status: valid" in rendered
        assert "Config is valid." in rendered
        assert "Warnings:" not in rendered

    def test_to_rich_valid_with_warnings(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=[
                "agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING).\nFix:\n- set agent.model"
            ],
            errors=[],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        rendered = rich_renderable.plain
        assert "Config: /workspace/.worktree/config.json" in rendered
        assert "Status: valid with warnings" in rendered
        assert "Warnings:" in rendered
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in rendered
        assert "Config is valid." in rendered

    def test_to_rich_invalid(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["paths.root_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID)."],
            warnings=[],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Config Validation Failed" in rendered
        assert "CONFIG_SEMANTIC_PATH_INVALID" in rendered

    def test_to_rich_invalid_with_warnings(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["semantic failure (CONFIG_ERROR)."],
            warnings=["warning message (CONFIG_WARN)."],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Config Validation Failed" in rendered
        assert "CONFIG_ERROR" in rendered
        assert "Warnings:" in rendered
        assert "CONFIG_WARN" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=["test-warning"],
            errors=[],
        )
        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["status"] == "valid"
        assert dumped["config_path"] == "/workspace/.worktree/config.json"
        assert dumped["warnings"] == ["test-warning"]
        assert dumped["errors"] == []


class ConfigSetFormatterTests:
    """Tests for ConfigSetFormatter."""

    def test_to_rich_ok(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="qwen2.5-coder",
            errors=[],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        rendered = rich_renderable.plain
        assert "Config updated: agent.model = qwen2.5-coder (str)" in rendered

    def test_to_rich_error(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.SCHEMA_INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.invalid_key",
            errors=["Config schema validation failed (CONFIG_SCHEMA_INVALID): extra property not allowed"],
        )
        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Config Error" in rendered
        assert "CONFIG_SCHEMA_INVALID" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="qwen2.5-coder",
            errors=[],
        )
        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["status"] == "ok"
        assert dumped["key"] == "agent.model"
        assert dumped["value"] == "qwen2.5-coder"


class ConfigRegistrationAndDispatchTests:
    """Tests for registration and dispatcher integration."""

    def test_register_config_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        assert ConfigLoadResult in dispatcher._registry
        assert WorktreeConfig in dispatcher._registry
        assert ConfigValidationResult in dispatcher._registry
        assert ConfigSetResult in dispatcher._registry
        assert isinstance(dispatcher._registry[WorktreeConfig], ConfigShowFormatter)
        assert isinstance(dispatcher._registry[ConfigValidationResult], ConfigValidateFormatter)
        assert isinstance(dispatcher._registry[ConfigSetResult], ConfigSetFormatter)

    def test_ui_dispatcher_registration(self) -> None:
        assert WorktreeConfig in ui_dispatcher._registry
        assert ConfigValidationResult in ui_dispatcher._registry
        assert ConfigSetResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[WorktreeConfig], ConfigShowFormatter)
        assert isinstance(ui_dispatcher._registry[ConfigValidationResult], ConfigValidateFormatter)
        assert isinstance(ui_dispatcher._registry[ConfigSetResult], ConfigSetFormatter)

    def test_dispatcher_config_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="ndjson-proj"))

        dispatcher.dispatch(config, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "WorktreeConfig"
        assert payload["payload"]["version"] == 1
        assert payload["payload"]["project"]["name"] == "ndjson-proj"

    def test_dispatcher_config_show_terminal(self, capsys: pytest.CaptureFixture[str]) -> None:
        console = Console(force_terminal=True, width=120)
        dispatcher = UiDispatcher(console=console)
        register_config_formatters(dispatcher)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="terminal-proj"))

        dispatcher.dispatch(config, output_format="terminal")

        captured = capsys.readouterr()
        assert "Config:" in captured.out
        assert "Status: valid" in captured.out
        assert "terminal-proj" in captured.out

    def test_dispatcher_config_validate_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="ndjson-validate")),
            warnings=["warn-1"],
            errors=[],
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigValidationResult"
        assert payload["payload"]["status"] == "valid"
        assert payload["payload"]["config_path"] == "/workspace/.worktree/config.json"
        assert payload["payload"]["warnings"] == ["warn-1"]

    def test_dispatcher_config_set_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="gpt-4o",
            errors=[],
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigSetResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["key"] == "agent.model"
        assert payload["payload"]["value"] == "gpt-4o"
