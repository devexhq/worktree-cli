"""Tier 2 presentation contract tests for ConfigSetFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.config.config_set import ConfigSetFormatter
from worktree.core.config.mutate import ConfigSetResult, ConfigSetStatus


class ConfigSetFormatterTests:
    """Tests for ConfigSetFormatter."""

    def test_to_rich_mutation_renders_key_and_value(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="qwen2.5-coder",
            errors=[],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "agent.model" in rendered
        assert "qwen2.5-coder" in rendered

    def test_to_rich_when_invalid_schema_renders_error_and_fix(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.SCHEMA_INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.invalid_key",
            errors=["Config schema validation failed (CONFIG_SCHEMA_INVALID): extra property not allowed"],
            fixes=["Run `wt config validate` for details"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_SCHEMA_INVALID" in rendered
        assert "Run `wt config validate` for details" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="qwen2.5-coder",
            errors=[],
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "config_path": "/workspace/.worktree/config.json",
            "key": "agent.model",
            "value": "qwen2.5-coder",
            "errors": [],
            "warnings": [],
            "fixes": [],
        }
