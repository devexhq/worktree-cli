"""Tests for config dot-path mutation helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from getworktree.core.config.generator import generate_default_config
from getworktree.core.config.mutate import (
    ConfigSetStatus,
    set_config_value_result,
    set_nested_value,
)


def _write_default_config(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    gen = generate_default_config(config_path, project_name=repo.name)
    assert gen.ok
    return config_path


def _read_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


class SetNestedValueTests:
    """Pure dict mutation tests for set_nested_value."""

    def test_sets_top_level_key(self) -> None:
        data: dict = {"version": 1}
        set_nested_value(data, "version", "2")
        assert data == {"version": "2"}

    def test_sets_existing_nested_key(self) -> None:
        data: dict = {"agent": {"model": "old", "provider": "local"}}
        set_nested_value(data, "agent.model", "qwen2.5-coder")
        assert data["agent"]["model"] == "qwen2.5-coder"
        assert data["agent"]["provider"] == "local"

    def test_creates_missing_intermediate_dicts(self) -> None:
        data: dict = {}
        set_nested_value(data, "custom.toolchain.timeout", "120")
        assert data == {"custom": {"toolchain": {"timeout": "120"}}}

    def test_type_collision_raises_and_preserves_dict(self) -> None:
        data: dict = {"agents": {"ollama": "qwen2.5-coder"}}
        snapshot = json.loads(json.dumps(data))
        with pytest.raises(ValueError, match="already defined as a scalar value"):
            set_nested_value(data, "agents.ollama.port", "11434")
        assert data == snapshot

    def test_empty_path_raises(self) -> None:
        data: dict = {}
        with pytest.raises(ValueError, match="non-empty"):
            set_nested_value(data, "", "x")

    def test_empty_segment_raises(self) -> None:
        data: dict = {}
        with pytest.raises(ValueError, match="empty segment"):
            set_nested_value(data, "agent..model", "x")


class SetConfigValueResultTests:
    """Filesystem-backed tests for set_config_value_result."""

    def test_sets_nested_key_and_preserves_siblings(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        before = _read_config(config_path)

        result = set_config_value_result(
            "agent.model",
            "qwen2.5-coder",
            cwd=tmp_path,
        )

        assert result.ok
        assert result.status is ConfigSetStatus.OK
        assert result.key == "agent.model"
        assert result.value == "qwen2.5-coder"
        assert result.config_path == config_path.resolve()

        after = _read_config(config_path)
        assert after["agent"]["model"] == "qwen2.5-coder"
        assert after["agent"]["provider"] == before["agent"]["provider"]
        assert after["project"]["name"] == before["project"]["name"]
        assert after["paths"] == before["paths"]

    def test_creates_new_nested_path(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        before = _read_config(config_path)

        result = set_config_value_result(
            "custom.toolchain.timeout",
            "120",
            cwd=tmp_path,
        )

        assert result.ok
        after = _read_config(config_path)
        assert after["custom"]["toolchain"]["timeout"] == "120"
        assert after["version"] == before["version"]

    def test_sets_typed_non_string_values(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)

        res_bool = set_config_value_result("agent.sandbox_enabled", True, cwd=tmp_path)
        assert res_bool.ok
        assert res_bool.value is True

        res_int = set_config_value_result("custom.timeout", 120, cwd=tmp_path)
        assert res_int.ok
        assert res_int.value == 120

        res_list = set_config_value_result("custom.items", [1, 2], cwd=tmp_path)
        assert res_list.ok
        assert res_list.value == [1, 2]

        data = _read_config(config_path)
        assert data["agent"]["sandbox_enabled"] is True
        assert data["custom"]["timeout"] == 120
        assert data["custom"]["items"] == [1, 2]

    def test_type_collision_does_not_write(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        data = _read_config(config_path)
        data["agents"] = {"ollama": "qwen2.5-coder"}
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        original = config_path.read_text(encoding="utf-8")

        result = set_config_value_result(
            "agents.ollama.port",
            "11434",
            cwd=tmp_path,
        )

        assert not result.ok
        assert result.status is ConfigSetStatus.TYPE_COLLISION
        assert "agents.ollama.port" in result.errors[0]
        assert "agents.ollama" in result.errors[0]
        assert "scalar" in result.errors[0]
        assert config_path.read_text(encoding="utf-8") == original

    def test_missing_config(self, tmp_path: Path) -> None:
        result = set_config_value_result("agent.model", "x", cwd=tmp_path)
        assert not result.ok
        assert result.status is ConfigSetStatus.NOT_FOUND
        assert "CONFIG_NOT_FOUND" in result.errors[0]

    def test_malformed_json(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{not-json\n", encoding="utf-8")

        result = set_config_value_result("agent.model", "x", cwd=tmp_path)
        assert not result.ok
        assert result.status is ConfigSetStatus.MALFORMED_JSON
        assert "CONFIG_MALFORMED_JSON" in result.errors[0]

    def test_root_not_object(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("[]\n", encoding="utf-8")

        result = set_config_value_result("agent.model", "x", cwd=tmp_path)
        assert not result.ok
        assert result.status is ConfigSetStatus.ROOT_NOT_OBJECT
        assert "CONFIG_ROOT_NOT_OBJECT" in result.errors[0]

    def test_top_level_key(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        result = set_config_value_result("version", "1", cwd=tmp_path)
        assert result.ok
        assert _read_config(config_path)["version"] == "1"

    def test_explicit_config_path(self, tmp_path: Path) -> None:
        config_path = tmp_path / "elsewhere" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"a": {"b": 1}}\n', encoding="utf-8")

        result = set_config_value_result(
            "a.b",
            "2",
            config_path=config_path,
        )
        assert result.ok
        assert _read_config(config_path) == {"a": {"b": "2"}}
