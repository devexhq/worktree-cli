"""Integration tests verifying config mutation, atomic updates, and type casting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.mutate import (
    ConfigSetResult,
    ConfigSetStatus,
    set_config_value_result,
)

pytestmark = pytest.mark.integration


class ConfigMutationTests:
    """Integration tests verifying config mutation, atomic updates, and type casting."""

    def test_set_dot_path_updates_scalar_value(self, isolated_workspace: Path) -> None:
        """Verify dot-path sets nested scalar value atomically and preserves siblings."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        result = set_config_value_result("agent.model", "qwen2.5-coder", path=isolated_workspace)

        assert_model_equal(
            result,
            ConfigSetResult(
                status=ConfigSetStatus.OK,
                config_path=config_path,
                key="agent.model",
                value="qwen2.5-coder",
                errors=[],
            ),
        )
        data = json.loads(config_path.read_text())
        assert data["agent"]["model"] == "qwen2.5-coder"
        assert data["agent"]["provider"] == payload["agent"]["provider"]

    def test_set_dot_path_converts_and_validates_types(self, isolated_workspace: Path) -> None:
        """Verify string "true" is converted to boolean True and invalid types are rejected."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        bool_result = set_config_value_result("telemetry.enabled", "true", path=isolated_workspace)
        assert_model_equal(
            bool_result,
            ConfigSetResult(
                status=ConfigSetStatus.OK,
                config_path=config_path,
                key="telemetry.enabled",
                value=True,
                errors=[],
            ),
        )
        assert json.loads(config_path.read_text())["telemetry"]["enabled"] is True

        schema_error_result = set_config_value_result(
            "sandbox.max_active_sandboxes", "not_an_int", path=isolated_workspace
        )
        assert_model_equal(
            schema_error_result,
            ConfigSetResult(
                status=ConfigSetStatus.SCHEMA_INVALID,
                config_path=config_path,
                key="sandbox.max_active_sandboxes",
                value="not_an_int",
                errors=[
                    "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- sandbox.max_active_sandboxes: 'not_an_int' is not of type 'integer'"
                ],
                fixes=[
                    "Run `wt config validate` for details",
                    "Or `wt init --repair` to insert missing keys without overwriting values",
                ],
            ),
        )
        assert json.loads(config_path.read_text())["sandbox"]["max_active_sandboxes"] == 3

        disk_data = json.loads(config_path.read_text())
        disk_data["agent"] = "scalar"
        Filesystem.atomic_write_json(config_path, disk_data)

        collision_result = set_config_value_result("agent.model", "qwen2.5-coder", path=isolated_workspace)
        assert_model_equal(
            collision_result,
            ConfigSetResult(
                status=ConfigSetStatus.TYPE_COLLISION,
                config_path=config_path,
                key="agent.model",
                value="qwen2.5-coder",
                errors=["Cannot set 'agent.model'. 'agent' is already defined as a scalar value."],
            ),
        )
