"""Tier 2 presentation contract tests for ConfigValidateFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.config import (
    ConfigValidateFormatter,
    ConfigValidationView,
)
from worktree.core.config.models import ProjectConfig, WorktreeConfig
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)

CONFIG_PATH = Path("/workspace/.worktree/config.json")

VALID_CASE = FormatterCase(
    data=ConfigValidationResult(
        status=ConfigValidationStatus.VALID,
        config_path=CONFIG_PATH,
        config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
        warnings=[],
        errors=[],
        fixes=[],
    ),
    view=ConfigValidationView(
        status=ConfigValidationStatus.VALID,
        config_path=CONFIG_PATH,
        status_label="valid",
        config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
        errors=[],
        warnings=[],
        fixes=[],
    ),
)

VALID_WITH_WARNINGS_CASE = FormatterCase(
    data=ConfigValidationResult(
        status=ConfigValidationStatus.VALID,
        config_path=CONFIG_PATH,
        config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
        warnings=["agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING)."],
        errors=[],
        fixes=["Set agent.model in .worktree/config.json"],
    ),
    view=ConfigValidationView(
        status=ConfigValidationStatus.VALID,
        config_path=CONFIG_PATH,
        status_label="valid with warnings",
        config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
        errors=[],
        warnings=["agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING)."],
        fixes=["Set agent.model in .worktree/config.json"],
    ),
)

INVALID_CASE = FormatterCase(
    data=ConfigValidationResult(
        status=ConfigValidationStatus.INVALID,
        config_path=CONFIG_PATH,
        errors=["paths.root_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID)."],
        warnings=[],
        fixes=["Use a plain relative path string without newlines or NUL bytes"],
    ),
    view=ConfigValidationView(
        status=ConfigValidationStatus.INVALID,
        config_path=CONFIG_PATH,
        status_label="invalid",
        config=None,
        errors=["paths.root_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID)."],
        warnings=[],
        fixes=["Use a plain relative path string without newlines or NUL bytes"],
    ),
)

INVALID_WITH_WARNINGS_CASE = FormatterCase(
    data=ConfigValidationResult(
        status=ConfigValidationStatus.INVALID,
        config_path=CONFIG_PATH,
        errors=["semantic failure (CONFIG_ERROR)."],
        warnings=["warning message (CONFIG_WARN)."],
        fixes=[],
    ),
    view=ConfigValidationView(
        status=ConfigValidationStatus.INVALID,
        config_path=CONFIG_PATH,
        status_label="invalid",
        config=None,
        errors=["semantic failure (CONFIG_ERROR)."],
        warnings=["warning message (CONFIG_WARN)."],
        fixes=[],
    ),
)

VALIDATION_CASES = [
    pytest.param(VALID_CASE, id="valid_config"),
    pytest.param(VALID_WITH_WARNINGS_CASE, id="valid_with_warnings"),
    pytest.param(INVALID_CASE, id="invalid_config"),
    pytest.param(INVALID_WITH_WARNINGS_CASE, id="invalid_with_warnings"),
]

VALIDATION_PAYLOAD_CASES = [
    pytest.param(
        VALID_CASE,
        {
            "status": "valid",
            "config_path": "/workspace/.worktree/config.json",
            "status_label": "valid",
            "raw": None,
            "config": {
                "version": 1,
                "project": {
                    "name": "valid-proj",
                    "initialized_at": None,
                },
                "paths": {
                    "root_dir": ".worktree",
                    "sessions_dir": ".worktree/sessions",
                    "artifacts_dir": ".worktree/artifacts",
                    "db_path": ".worktree/data.db",
                },
                "sandbox": {
                    "base_ref": "HEAD",
                    "max_active_sandboxes": 3,
                    "default_timeout_seconds": 900,
                },
                "agent": {
                    "provider": "local",
                    "model": None,
                    "endpoint": None,
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
                "history": {
                    "save_attempt_logs": True,
                    "save_agent_payloads": True,
                    "save_final_diff": True,
                    "max_sessions": 1000,
                },
                "doctor": {
                    "check_git": True,
                    "check_paths_writable": True,
                    "check_config_schema": True,
                    "check_stale_worktrees": True,
                    "check_required_binaries": True,
                },
                "prune": {
                    "remove_stale_worktrees": True,
                    "remove_orphaned_sandboxes": True,
                    "remove_expired_artifacts": False,
                    "artifact_ttl_days": 30,
                },
                "telemetry": {
                    "enabled": False,
                },
                "concurrency": {
                    "lock_timeout_seconds": 30.0,
                },
            },
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="valid_payload",
    ),
    pytest.param(
        INVALID_CASE,
        {
            "status": "invalid",
            "config_path": "/workspace/.worktree/config.json",
            "status_label": "invalid",
            "raw": None,
            "config": None,
            "errors": ["paths.root_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID)."],
            "warnings": [],
            "fixes": ["Use a plain relative path string without newlines or NUL bytes"],
        },
        id="invalid_payload",
    ),
]


class ConfigValidateFormatterTests:
    """Presentation contract tests for ConfigValidateFormatter."""

    @pytest.mark.parametrize("case", VALIDATION_CASES)
    def test_transform_derives_expected_view(
        self, case: FormatterCase[ConfigValidationResult, ConfigValidationView]
    ) -> None:
        """Verify transform derives the exact ConfigValidationView model representation."""
        assert ConfigValidateFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), VALIDATION_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[ConfigValidationResult, ConfigValidationView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert ConfigValidateFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", VALIDATION_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[ConfigValidationResult, ConfigValidationView]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(ConfigValidateFormatter().to_rich(case.data))
        view = case.view

        if view.status == ConfigValidationStatus.VALID:
            assert view.config_path.as_posix() in rendered
            assert view.status_label in rendered
        for error in view.errors:
            assert error in rendered
        for warning in view.warnings:
            assert warning in rendered
        for fix in view.fixes:
            assert fix in rendered
