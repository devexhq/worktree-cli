"""Tier 2 presentation contract tests for ConfigValidateFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.config.config_validate import ConfigValidateFormatter
from worktree.core.config.models import ProjectConfig, WorktreeConfig
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)


class ConfigValidateFormatterTests:
    """Tests for ConfigValidateFormatter."""

    def test_to_rich_valid_renders_config_path(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=[],
            errors=[],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "/workspace/.worktree/config.json" in rendered

    def test_to_rich_valid_with_warnings_renders_path_and_warning(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=[
                "agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING).\nFix:\n- set agent.model"
            ],
            errors=[],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "/workspace/.worktree/config.json" in rendered
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in rendered

    def test_to_rich_when_invalid_renders_error_and_fix(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["paths.root_dir contains invalid control characters (CONFIG_SEMANTIC_PATH_INVALID)."],
            warnings=[],
            fixes=["Use a plain relative path string without newlines or NUL bytes"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_SEMANTIC_PATH_INVALID" in rendered
        assert "Use a plain relative path string without newlines or NUL bytes" in rendered

    def test_to_rich_when_invalid_with_warnings_renders_error_and_warning(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=Path("/workspace/.worktree/config.json"),
            errors=["semantic failure (CONFIG_ERROR)."],
            warnings=["warning message (CONFIG_WARN)."],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_ERROR" in rendered
        assert "CONFIG_WARN" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="valid-proj")),
            warnings=["test-warning"],
            errors=[],
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "valid",
            "config_path": "/workspace/.worktree/config.json",
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
            "warnings": ["test-warning"],
            "errors": [],
            "fixes": [],
        }
