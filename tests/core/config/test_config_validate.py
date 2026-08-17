"""Tests for the non-raising config validation engine."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.config.generator import (
    build_default_config,
    generate_default_config,
)
from worktree.core.config.validate import (
    ConfigValidationStatus,
    validate_config_result,
)


def _write_config(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _joined(result) -> str:
    return "\n".join([*result.errors, *result.warnings])


class ValidateConfigResultSuccessTests:
    """Success paths for validate_config_result."""

    def test_valid_after_init_defaults(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "demo").ok
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.VALID
        assert result.ok
        assert result.config_path == config_path.resolve()
        assert result.raw is not None
        assert result.config is not None
        assert result.config.project.name == "demo"
        assert result.errors == []
        assert result.warnings == []
        on_disk = json.loads(config_path.read_text(encoding="utf-8"))
        assert on_disk == result.raw

    def test_explicit_config_path_wins(self, fs: FileSystem) -> None:
        alt = fs.base_path / "elsewhere" / "config.json"
        alt.parent.mkdir(parents=True)
        assert generate_default_config(alt, "alt-demo").ok
        result = validate_config_result(cwd=fs.base_path, config_path=alt)
        assert result.ok
        assert result.config is not None
        assert result.config.project.name == "alt-demo"
        assert result.config_path == alt.resolve()


class ValidateConfigResultLoadFailureTests:
    """IO/parse failure passthrough from the loader stack."""

    def test_not_found(self, fs: FileSystem) -> None:
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.NOT_FOUND
        assert not result.ok
        assert result.config is None
        assert result.raw is None
        assert result.warnings == []
        joined = _joined(result)
        assert "CONFIG_NOT_FOUND" in joined
        assert "wt init" in joined
        assert str(result.config_path) in joined

    def test_malformed_json(self, fs: FileSystem) -> None:
        path = _write_config(fs.base_path / ".worktree" / "config.json", "{not-json")
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.MALFORMED_JSON
        assert not result.ok
        assert result.warnings == []
        assert any("CONFIG_MALFORMED_JSON" in e for e in result.errors)
        assert any(str(path.resolve()) in e for e in result.errors)

    def test_root_not_object(self, fs: FileSystem) -> None:
        _write_config(fs.base_path / ".worktree" / "config.json", [])
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.ROOT_NOT_OBJECT
        assert not result.ok
        assert result.warnings == []
        assert any("CONFIG_ROOT_NOT_OBJECT" in e for e in result.errors)

    def test_path_is_directory(self, fs: FileSystem) -> None:
        path = fs.base_path / ".worktree" / "config.json"
        path.mkdir(parents=True)
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.PATH_IS_DIRECTORY
        assert not result.ok
        assert result.warnings == []
        assert any("CONFIG_PATH_IS_DIRECTORY" in e for e in result.errors)

    def test_unreadable(self, fs: FileSystem) -> None:
        path = _write_config(
            fs.base_path / ".worktree" / "config.json",
            build_default_config("demo"),
        )
        path.chmod(0)
        try:
            result = validate_config_result(cwd=fs.base_path)
            if os.access(path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            assert result.status == ConfigValidationStatus.UNREADABLE
            assert not result.ok
            assert result.warnings == []
            assert any("CONFIG_UNREADABLE" in e for e in result.errors)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_schema_invalid_grouped(self, fs: FileSystem) -> None:
        raw = {"version": 1}
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.INVALID
        assert not result.ok
        assert result.config is None
        assert result.raw == raw
        assert result.warnings == []
        assert len(result.errors) == 1
        block = result.errors[0]
        assert "CONFIG_SCHEMA_INVALID" in block
        assert "Config schema validation failed" in block
        assert block.count("CONFIG_SCHEMA_INVALID") == 1
        assert "- " in block
        assert "wt config validate" in block
        assert "wt init --repair" in block


class ValidateConfigResultSemanticErrorTests:
    """Semantic error rules after structural pass."""

    def test_path_invalid_control_characters(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["paths"]["sessions_dir"] = ".worktree/sessions\nbad"
        raw["paths"]["db_path"] = ".worktree/token\x00audit.db"
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.INVALID
        assert not result.ok
        assert len(result.errors) == 2
        assert all("CONFIG_SEMANTIC_PATH_INVALID" in e for e in result.errors)
        assert "paths.db_path" in result.errors[0]
        assert "paths.sessions_dir" in result.errors[1]
        assert all("Fix:" in e for e in result.errors)


class ValidateConfigResultSemanticWarningTests:
    """Semantic warning rules that keep ok=true when alone."""

    def test_agent_model_missing_for_non_local(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["agent"]["provider"] = "openai"
        raw["agent"]["model"] = None
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.VALID
        assert result.ok
        assert result.config is not None
        assert result.errors == []
        assert len(result.warnings) == 1
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in result.warnings[0]
        assert "Fix:" in result.warnings[0]

    def test_local_provider_null_model_no_warning(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        assert raw["agent"]["provider"] == "local"
        assert raw["agent"]["model"] is None
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.ok
        assert result.warnings == []

    def test_agent_endpoint_not_http(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["agent"]["endpoint"] = "ftp://example.com/api"
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.ok
        assert result.errors == []
        assert any("CONFIG_WARN_AGENT_ENDPOINT" in w for w in result.warnings)
        assert any("Fix:" in w for w in result.warnings)

    def test_null_endpoint_no_warning(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["agent"]["endpoint"] = None
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.ok
        assert not any("CONFIG_WARN_AGENT_ENDPOINT" in w for w in result.warnings)

    def test_sandbox_limit_warning(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["sandbox"]["max_active_sandboxes"] = 11
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.ok
        assert result.errors == []
        assert len(result.warnings) == 1
        assert "CONFIG_WARN_SANDBOX_LIMIT" in result.warnings[0]
        assert "11" in result.warnings[0]
        assert "Fix:" in result.warnings[0]

    def test_warning_order(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["agent"]["provider"] = "anthropic"
        raw["agent"]["model"] = None
        raw["agent"]["endpoint"] = "not-a-url"
        raw["sandbox"]["max_active_sandboxes"] = 20
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.ok
        assert len(result.warnings) == 3
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in result.warnings[0]
        assert "CONFIG_WARN_AGENT_ENDPOINT" in result.warnings[1]
        assert "CONFIG_WARN_SANDBOX_LIMIT" in result.warnings[2]

    def test_semantic_errors_with_warnings(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["paths"]["root_dir"] = "root\x00dir"
        raw["agent"]["provider"] = "custom"
        raw["agent"]["model"] = None
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = validate_config_result(cwd=fs.base_path)
        assert result.status == ConfigValidationStatus.INVALID
        assert not result.ok
        assert result.config is None
        assert any("CONFIG_SEMANTIC_PATH_INVALID" in e for e in result.errors)
        assert any("CONFIG_WARN_AGENT_MODEL_MISSING" in w for w in result.warnings)
