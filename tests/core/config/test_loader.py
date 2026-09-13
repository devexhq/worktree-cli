from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.loader import (
    ConfigLoadResult,
    ConfigLoadStatus,
    load_config,
)
from worktree.core.config.models import WorktreeConfig

pytestmark = pytest.mark.integration

SCHEMA_VIOLATION_PAYLOADS = [
    pytest.param(
        {"version": 1},
        id="missing_sections",
    ),
    pytest.param(
        {
            "version": 1,
            "project": {"name": "test-project"},
            "sandbox": {"max_active_sandboxes": "five"},
        },
        id="invalid_types",
    ),
    pytest.param(
        {
            **build_default_config("test-project"),
            "version": 99,
        },
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

        assert_model_equal(
            result,
            ConfigLoadResult(
                status=ConfigLoadStatus.OK,
                config_path=config_path,
                raw=payload,
                config=WorktreeConfig.model_validate(payload),
            ),
        )

    def test_load_missing_config_returns_failure_result(self, isolated_workspace: Path) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"

        result = load_config(isolated_workspace)

        assert_model_equal(
            result,
            ConfigLoadResult(
                status=ConfigLoadStatus.NOT_FOUND,
                config_path=config_path,
                errors=[f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND)."],
                fixes=["Run `wt init` to create `.worktree/config.json`"],
            ),
        )

    @pytest.mark.parametrize("payload", SCHEMA_VIOLATION_PAYLOADS)
    def test_load_schema_violation_returns_validation_errors(
        self,
        isolated_workspace: Path,
        payload: dict[str, Any],
    ) -> None:
        config_path = isolated_workspace / ".worktree" / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = load_config(isolated_workspace)

        assert_model_equal(
            result,
            ConfigLoadResult(
                status=ConfigLoadStatus.SCHEMA_INVALID,
                config_path=config_path,
                raw=payload,
                fixes=[
                    "Run `wt config validate` for details",
                    "Or `wt init --repair` to insert missing keys without overwriting values",
                ],
            ),
            exclude={"errors"},
        )
