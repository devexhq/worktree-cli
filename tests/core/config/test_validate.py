from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.assertions import assert_result_error, assert_result_ok
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.validate import (
    ConfigValidationStatus,
    validate_config_result,
)

pytestmark = pytest.mark.unit


class ConfigSemanticValidationTests:
    """Unit tests verifying semantic validation rules and warning generation."""

    def test_validate_config_detects_null_bytes_and_newlines_in_paths(self, tmp_path: Path) -> None:
        payload = build_default_config("demo")
        payload["paths"]["db_path"] = "state\x00.db"
        payload["paths"]["sessions_dir"] = "sessions\ndir"
        config_path = tmp_path / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = validate_config_result(config_path=config_path)

        assert_result_error(
            result,
            expected_code="CONFIG_SEMANTIC_PATH_INVALID",
            expected_status=ConfigValidationStatus.INVALID,
        )
        assert result.errors == [
            "paths.db_path contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID).",
            "paths.sessions_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID).",
        ]
        assert result.fixes == [
            "Use a plain relative path string without newlines or NUL bytes",
            "Use a plain relative path string without newlines or NUL bytes",
        ]

    def test_validate_config_warns_when_non_local_agent_has_no_model(self, tmp_path: Path) -> None:
        payload = build_default_config("demo")
        payload["agent"]["provider"] = "openai"
        payload["agent"]["model"] = None
        config_path = tmp_path / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = validate_config_result(config_path=config_path)

        assert_result_ok(result, expected_status=ConfigValidationStatus.VALID)
        assert result.warnings == [
            "agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING)."
        ]
        assert result.fixes == ["Set agent.model or use provider=local"]

    def test_validate_config_warns_when_agent_endpoint_is_not_absolute_url(self, tmp_path: Path) -> None:
        payload = build_default_config("demo")
        payload["agent"]["endpoint"] = "ftp://example.com/api"
        config_path = tmp_path / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = validate_config_result(config_path=config_path)

        assert_result_ok(result, expected_status=ConfigValidationStatus.VALID)
        assert result.warnings == [
            "agent.endpoint is not an absolute http(s) URL: 'ftp://example.com/api' (CONFIG_WARN_AGENT_ENDPOINT)."
        ]
        assert result.fixes == ["Set agent.endpoint to an absolute http:// or https:// URL, or null"]

    def test_validate_config_warns_when_sandbox_limit_exceeds_threshold(self, tmp_path: Path) -> None:
        payload = build_default_config("demo")
        payload["sandbox"]["max_active_sandboxes"] = 11
        config_path = tmp_path / "config.json"
        Filesystem.atomic_write_json(config_path, payload)

        result = validate_config_result(config_path=config_path)

        assert_result_ok(result, expected_status=ConfigValidationStatus.VALID)
        assert result.warnings == ["sandbox.max_active_sandboxes (11) exceeds 10 (CONFIG_WARN_SANDBOX_LIMIT)."]
        assert result.fixes == ["Lower sandbox.max_active_sandboxes to 10 or fewer"]
