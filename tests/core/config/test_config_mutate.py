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
            "agent.endpoint",
            "http://localhost:11434",
            cwd=tmp_path,
        )

        assert result.ok
        after = _read_config(config_path)
        assert after["agent"]["endpoint"] == "http://localhost:11434"
        assert after["version"] == before["version"]

    def test_sets_typed_non_string_values(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)

        res_bool = set_config_value_result("sandbox.auto_clean", False, cwd=tmp_path)
        assert res_bool.ok
        assert res_bool.value is False

        res_int = set_config_value_result(
            "sandbox.max_active_sandboxes", 5, cwd=tmp_path
        )
        assert res_int.ok
        assert res_int.value == 5

        res_float = set_config_value_result("agent.temperature", 0.7, cwd=tmp_path)
        assert res_float.ok
        assert res_float.value == 0.7

        data = _read_config(config_path)
        assert data["sandbox"]["auto_clean"] is False
        assert data["sandbox"]["max_active_sandboxes"] == 5
        assert data["agent"]["temperature"] == 0.7

    def test_invalid_schema_key_does_not_write(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        original = config_path.read_text(encoding="utf-8")

        result = set_config_value_result(
            "sandboxes.max_active_sandboxes",
            3,
            cwd=tmp_path,
        )

        assert not result.ok
        assert result.status is ConfigSetStatus.SCHEMA_INVALID
        assert "CONFIG_SCHEMA_INVALID" in result.errors[0]
        assert "sandboxes" in result.errors[0]
        assert config_path.read_text(encoding="utf-8") == original

    def test_invalid_schema_value_does_not_write(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        original = config_path.read_text(encoding="utf-8")

        result = set_config_value_result(
            "sandbox.max_active_sandboxes",
            -1,
            cwd=tmp_path,
        )

        assert not result.ok
        assert result.status is ConfigSetStatus.SCHEMA_INVALID
        assert "CONFIG_SCHEMA_INVALID" in result.errors[0]
        assert config_path.read_text(encoding="utf-8") == original

    def test_type_collision_does_not_write(self, tmp_path: Path) -> None:
        config_path = _write_default_config(tmp_path)
        data = _read_config(config_path)
        data["agent"] = "scalar-value"
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        original = config_path.read_text(encoding="utf-8")

        result = set_config_value_result(
            "agent.model",
            "qwen2.5-coder",
            cwd=tmp_path,
        )

        assert not result.ok
        assert result.status is ConfigSetStatus.TYPE_COLLISION
        assert "agent.model" in result.errors[0]
        assert "agent" in result.errors[0]
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
        result = set_config_value_result("version", 1, cwd=tmp_path)
        assert result.ok
        assert _read_config(config_path)["version"] == 1

    def test_explicit_config_path(self, tmp_path: Path) -> None:
        explicit_dir = tmp_path / "elsewhere"
        config_path = _write_default_config(explicit_dir)

        result = set_config_value_result(
            "sandbox.max_active_sandboxes",
            5,
            config_path=config_path,
        )
        assert result.ok
        assert _read_config(config_path)["sandbox"]["max_active_sandboxes"] == 5

    def test_write_failed_on_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = _write_default_config(tmp_path)
        original_text = config_path.read_text(encoding="utf-8")

        def mock_write_json(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(
            "getworktree.core.config.mutate.atomic_write_json", mock_write_json
        )

        result = set_config_value_result("agent.model", "qwen2.5-coder", cwd=tmp_path)
        assert not result.ok
        assert result.status is ConfigSetStatus.WRITE_FAILED
        assert "CONFIG_WRITE_FAILED" in result.errors[0]
        assert "Permission denied" in result.errors[0]
        assert "check file permissions and free disk space" in result.errors[0]
        assert config_path.read_text(encoding="utf-8") == original_text
