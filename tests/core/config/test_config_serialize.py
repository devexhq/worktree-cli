"""Tests for config serialization helpers."""

from __future__ import annotations

import json
from typing import Any

from getworktree.core.config.generator import (
    CANONICAL_V1_DEFAULTS,
    build_default_config,
)
from getworktree.core.config.loader import parse_and_validate_config
from getworktree.core.config.models import WorktreeConfig
from getworktree.core.config.serialize import as_json, serialize_config

_TOP_LEVEL = (
    "version",
    "project",
    "paths",
    "sandbox",
    "loop",
    "agent",
    "patch",
    "approval",
    "history",
    "doctor",
    "prune",
    "telemetry",
)


def _config_from_defaults(name: str = "demo") -> WorktreeConfig:
    return parse_and_validate_config(build_default_config(name))


class SerializeConfigTests:
    """Tests for serialize_config."""

    def test_includes_every_top_level_section(self) -> None:
        data = serialize_config(_config_from_defaults())
        assert list(data.keys()) == list(_TOP_LEVEL)

    def test_nested_keys_match_canonical_defaults(self) -> None:
        data = serialize_config(_config_from_defaults())
        for section, defaults in CANONICAL_V1_DEFAULTS.items():
            if section in {"version", "project"}:
                continue
            assert isinstance(defaults, dict)
            assert list(data[section].keys()) == list(defaults.keys())

    def test_null_project_name_is_normalized_string(self) -> None:
        raw = build_default_config("demo")
        raw["project"]["name"] = None
        data = serialize_config(parse_and_validate_config(raw))
        assert data["project"]["name"] == "unnamed_project"
        assert data["project"]["name"] is not None

    def test_optional_strings_remain_json_null(self) -> None:
        data = serialize_config(_config_from_defaults())
        assert data["agent"]["model"] is None
        assert data["agent"]["endpoint"] is None

    def test_native_scalar_types(self) -> None:
        data = serialize_config(_config_from_defaults())
        assert data["version"] == 1
        assert data["sandbox"]["auto_clean"] is True
        assert data["loop"]["default_max_attempts"] == 5
        assert data["agent"]["temperature"] == 0.2
        assert isinstance(data["agent"]["temperature"], float)

    def test_defaults_applied_for_omitted_model_sections(self) -> None:
        """WorktreeConfig factories fill omitted optional sections."""
        config = WorktreeConfig(
            version=1,
            project={"name": "sparse", "initialized_at": None},
        )
        data = serialize_config(config)
        assert data["paths"]["root_dir"] == ".worktree"
        assert data["telemetry"]["enabled"] is False
        assert data["loop"]["default_max_attempts"] == 5

    def test_round_trip_json_types(self) -> None:
        data = serialize_config(_config_from_defaults())
        restored: dict[str, Any] = json.loads(json.dumps(data))
        assert restored == data


class AsJsonTests:
    """Tests for as_json."""

    def test_pretty_json_with_trailing_newline(self) -> None:
        text = as_json(_config_from_defaults("fmt"))
        assert text.endswith("\n")
        parsed = json.loads(text)
        assert parsed["project"]["name"] == "fmt"
        assert list(parsed.keys()) == list(_TOP_LEVEL)

    def test_two_space_indent(self) -> None:
        text = as_json(_config_from_defaults())
        assert '\n  "version"' in text or text.startswith('{\n  "version"')
