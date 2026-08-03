"""Tests for the hardened config V1 JSON Schema contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from getworktree.common.schema_validation import CONFIG_VALIDATOR
from getworktree.core.config.generator import (
    CANONICAL_V1_DEFAULTS,
    build_default_config,
    generate_default_config,
)
from getworktree.core.config.loader import (
    ConfigLoadStatus,
    load_config_result,
    parse_and_validate_config,
)
from getworktree.core.config.models import WorktreeConfig


def _valid_config() -> dict[str, Any]:
    return build_default_config("demo")


def _mutate(path: str, value: Any) -> dict[str, Any]:
    """Return a deep copy of a valid config with ``path`` set to ``value``."""
    data = _valid_config()
    parts = path.split(".")
    cursor: Any = data
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value
    return data


def _assert_schema_error(data: dict[str, Any], *path_fragments: str) -> list[str]:
    result = CONFIG_VALIDATOR.validate(data)
    assert not result.ok, f"expected schema failure, got ok for {data!r}"
    assert result.errors
    joined = "\n".join(result.errors)
    for fragment in path_fragments:
        assert fragment in joined, f"missing {fragment!r} in errors:\n{joined}"
    for error in result.errors:
        assert ": " in error
        path = error.split(": ", 1)[0]
        assert path  # path-qualified: dotted path or (root)
    return result.errors


class ConfigV1SchemaAcceptTests:
    """Valid documents must pass CONFIG_VALIDATOR."""

    def test_canonical_defaults_with_runtime_fields(self) -> None:
        result = CONFIG_VALIDATOR.validate(build_default_config("demo"))
        assert result.ok
        assert result.errors == []

    def test_canonical_v1_defaults_null_project_fields(self) -> None:
        # Raw defaults keep null project fields; schema allows null.
        result = CONFIG_VALIDATOR.validate(copy.deepcopy(CANONICAL_V1_DEFAULTS))
        assert result.ok, result.errors

    def test_all_allowed_providers(self) -> None:
        for provider in (
            "local",
            "ollama",
            "cursor",
            "openai",
            "anthropic",
            "azure_openai",
            "custom",
        ):
            data = _mutate("agent.provider", provider)
            assert CONFIG_VALIDATOR.validate(data).ok, provider

    def test_unified_diff_strategy(self) -> None:
        data = _mutate("patch.strategy", "unified_diff")
        assert CONFIG_VALIDATOR.validate(data).ok


class ConfigV1SchemaRejectTests:
    """Each major invalid class must fail with path-qualified errors."""

    def test_missing_top_level_key(self) -> None:
        data = _valid_config()
        del data["telemetry"]
        _assert_schema_error(data, "(root)")

    def test_missing_nested_key(self) -> None:
        data = _valid_config()
        del data["loop"]["default_max_attempts"]
        _assert_schema_error(data, "loop")

    def test_unknown_root_property(self) -> None:
        data = _valid_config()
        data["extra_root"] = True
        _assert_schema_error(data, "(root)")

    def test_unknown_nested_property(self) -> None:
        data = _valid_config()
        data["agent"]["mystery"] = "x"
        _assert_schema_error(data, "agent")

    def test_version_not_one(self) -> None:
        _assert_schema_error(_mutate("version", 2), "version")

    def test_wrong_types(self) -> None:
        _assert_schema_error(
            _mutate("loop.default_max_attempts", "five"),
            "loop.default_max_attempts",
        )
        _assert_schema_error(
            _mutate("sandbox.auto_clean", "yes"),
            "sandbox.auto_clean",
        )

    def test_empty_path_strings(self) -> None:
        for field in (
            "root_dir",
            "loops_dir",
            "sessions_dir",
            "artifacts_dir",
            "db_path",
        ):
            _assert_schema_error(_mutate(f"paths.{field}", ""), f"paths.{field}")

    def test_empty_sandbox_base_ref(self) -> None:
        _assert_schema_error(_mutate("sandbox.base_ref", ""), "sandbox.base_ref")

    def test_invalid_provider_enum(self) -> None:
        _assert_schema_error(
            _mutate("agent.provider", "not-a-provider"),
            "agent.provider",
        )

    def test_invalid_patch_strategy_enum(self) -> None:
        _assert_schema_error(
            _mutate("patch.strategy", "git_apply"),
            "patch.strategy",
        )

    def test_numeric_out_of_range(self) -> None:
        _assert_schema_error(
            _mutate("loop.default_max_attempts", 0),
            "loop.default_max_attempts",
        )
        _assert_schema_error(
            _mutate("agent.temperature", -0.1),
            "agent.temperature",
        )
        _assert_schema_error(
            _mutate("agent.temperature", 2.1),
            "agent.temperature",
        )
        _assert_schema_error(
            _mutate("agent.max_tokens", 0),
            "agent.max_tokens",
        )
        _assert_schema_error(
            _mutate("prune.artifact_ttl_days", -1),
            "prune.artifact_ttl_days",
        )

    def test_empty_optional_agent_strings(self) -> None:
        _assert_schema_error(_mutate("agent.model", ""), "agent.model")
        _assert_schema_error(_mutate("agent.endpoint", ""), "agent.endpoint")


class ConfigV1ModelAlignmentTests:
    """Pydantic models stay aligned with schema enums/bounds/strictness."""

    def test_model_accepts_generated_defaults(self) -> None:
        config = parse_and_validate_config(build_default_config("demo"))
        assert config.agent.provider == "local"
        assert config.patch.strategy == "unified_diff"
        assert config.agent.temperature == 0.2

    def test_model_rejects_unknown_keys(self) -> None:
        raw = build_default_config("demo")
        raw["agent"]["mystery"] = "nope"
        with pytest.raises(ValidationError):
            WorktreeConfig.model_validate(
                {
                    **raw,
                    "project": {
                        **raw["project"],
                        "name": raw["project"]["name"] or "unnamed_project",
                    },
                }
            )

    def test_model_rejects_invalid_provider(self) -> None:
        raw = build_default_config("demo")
        raw["agent"]["provider"] = "not-a-provider"
        with pytest.raises(ValidationError):
            WorktreeConfig.model_validate(
                {
                    **raw,
                    "project": {**raw["project"], "name": "demo"},
                }
            )

    def test_model_rejects_temperature_out_of_range(self) -> None:
        raw = build_default_config("demo")
        raw["agent"]["temperature"] = 3.0
        with pytest.raises(ValidationError):
            WorktreeConfig.model_validate(
                {
                    **raw,
                    "project": {**raw["project"], "name": "demo"},
                }
            )


class ConfigV1LoaderCompatibilityTests:
    """Loader still maps schema outcomes correctly."""

    def test_loader_ok_on_generated_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "demo").ok
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.OK
        assert result.config is not None

    def test_loader_schema_invalid_on_unknown_key(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        data = build_default_config("demo")
        data["extra"] = 1
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID
        joined = "\n".join(result.errors)
        assert "CONFIG_SCHEMA_INVALID" in joined
        assert "(root)" in joined or "extra" in joined
