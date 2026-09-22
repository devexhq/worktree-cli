from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.loader import (
    ConfigLoadStatus,
    load_config,
)
from worktree.core.config.models import WorktreeConfig

SCHEMA_VIOLATION_PAYLOADS = [
    pytest.param(
        {"version": 1},
        ("Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- (root): 'project' is a required property"),
        id="missing_sections",
    ),
    pytest.param(
        {
            "version": 1,
            "project": {"name": "test-project"},
            "sandbox": {"max_active_sandboxes": "five"},
        },
        (
            "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n"
            "- sandbox.max_active_sandboxes: 'five' is not of type 'integer'"
        ),
        id="invalid_types",
    ),
    pytest.param(
        {
            **build_default_config("test-project"),
            "version": 99,
        },
        "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- version: 1 was expected",
        id="unsupported_version",
    ),
]


class ConfigLoaderTests:
    """Integration tests verifying config.json loading and schema parsing contracts."""

    def test_load_returns_strongly_typed_worktree_config(self, isolated_workspace: Path) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        result = load_config(isolated_workspace)

        assert result.status == ConfigLoadStatus.OK
        assert result.config_path == config_path
        assert result.raw == payload
        assert result.config == WorktreeConfig.model_validate(payload)
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    def test_load_missing_config_returns_failure_result(self, isolated_workspace: Path) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"

        result = load_config(isolated_workspace)

        assert result.status == ConfigLoadStatus.NOT_FOUND
        assert result.config_path == config_path
        assert result.raw is None
        assert result.config is None
        assert result.errors == [f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND)."]
        assert result.warnings == []
        assert result.fixes == ["Run `wt init` to create `.worktree/config.json`"]

    def test_load_config_defaults_ignore_global_root_error_to_false(self, isolated_workspace: Path) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"
        legacy_payload = build_default_config("demo-workspace")
        legacy_payload.pop("ignore_global_root_error")
        Filesystem.atomic_write_json(config_path, legacy_payload)

        result = load_config(isolated_workspace)
        generated_payload = build_default_config("demo-workspace")

        assert result.status == ConfigLoadStatus.OK
        assert result.config is not None
        assert result.config.ignore_global_root_error is False
        assert generated_payload["ignore_global_root_error"] is False

    def test_load_config_accepts_boolean_ignore_global_root_error(self, isolated_workspace: Path) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"
        enabled_payload = build_default_config("demo-workspace")
        enabled_payload["ignore_global_root_error"] = True
        Filesystem.atomic_write_json(config_path, enabled_payload)

        enabled_result = load_config(isolated_workspace)

        invalid_payload = build_default_config("demo-workspace")
        invalid_payload["ignore_global_root_error"] = "true"
        Filesystem.atomic_write_json(config_path, invalid_payload)
        invalid_result = load_config(isolated_workspace, bypass_cache=True)

        assert enabled_result.status == ConfigLoadStatus.OK
        assert enabled_result.config is not None
        assert enabled_result.config.ignore_global_root_error is True
        assert invalid_result.status == ConfigLoadStatus.SCHEMA_INVALID
        assert "is not of type 'boolean'" in invalid_result.errors[0]

    @pytest.mark.parametrize(("payload", "expected_error"), SCHEMA_VIOLATION_PAYLOADS)
    def test_load_schema_violation_returns_validation_errors(
        self,
        isolated_workspace: Path,
        payload: dict[str, Any],
        expected_error: str,
    ) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = load_config(isolated_workspace)

        assert result.status == ConfigLoadStatus.SCHEMA_INVALID
        assert result.config_path == config_path
        assert result.raw == payload
        assert result.config is None
        assert result.errors == [expected_error]
        assert result.warnings == []
        assert result.fixes == [
            "Run `wt config validate` for details",
            "Or `wt init --repair` to insert missing keys without overwriting values",
        ]
