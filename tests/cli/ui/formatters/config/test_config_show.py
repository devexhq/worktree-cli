"""Tier 2 presentation contract tests for ConfigShowFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.config import ConfigShowFormatter, ConfigShowView
from worktree.core.config.loader import resolve_config_path
from worktree.core.config.models import AgentConfig, ProjectConfig, WorktreeConfig

RESOLVED_CONFIG_PATH = resolve_config_path()

DEFAULT_CONFIG_CASE = FormatterCase(
    data=WorktreeConfig(
        version=1,
        project=ProjectConfig(name="test-show-app"),
        agent=AgentConfig(model="gemini-2.5-pro"),
    ),
    view=ConfigShowView(
        config_path=RESOLVED_CONFIG_PATH,
        status="valid",
        config=WorktreeConfig(
            version=1,
            project=ProjectConfig(name="test-show-app"),
            agent=AgentConfig(model="gemini-2.5-pro"),
        ),
    ),
)

CUSTOM_CONFIG_CASE = FormatterCase(
    data=WorktreeConfig(
        version=1,
        project=ProjectConfig(name="custom-project"),
    ),
    view=ConfigShowView(
        config_path=RESOLVED_CONFIG_PATH,
        status="valid",
        config=WorktreeConfig(
            version=1,
            project=ProjectConfig(name="custom-project"),
        ),
    ),
)

SHOW_CASES = [
    pytest.param(DEFAULT_CONFIG_CASE, id="default_config"),
    pytest.param(CUSTOM_CONFIG_CASE, id="custom_config"),
]

SHOW_PAYLOAD_CASES = [
    pytest.param(
        DEFAULT_CONFIG_CASE,
        {
            "config_path": RESOLVED_CONFIG_PATH.as_posix(),
            "status": "valid",
            "config": {
                "version": 1,
                "project": {
                    "name": "test-show-app",
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
                    "model": "gemini-2.5-pro",
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
        },
        id="default_config_payload",
    ),
    pytest.param(
        CUSTOM_CONFIG_CASE,
        {
            "config_path": RESOLVED_CONFIG_PATH.as_posix(),
            "status": "valid",
            "config": {
                "version": 1,
                "project": {
                    "name": "custom-project",
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
        },
        id="custom_config_payload",
    ),
]


class ConfigShowFormatterTests:
    """Presentation contract tests for ConfigShowFormatter."""

    @pytest.mark.parametrize("case", SHOW_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[WorktreeConfig, ConfigShowView]) -> None:
        """Verify transform derives the exact ConfigShowView model representation."""
        assert ConfigShowFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), SHOW_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WorktreeConfig, ConfigShowView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert ConfigShowFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", SHOW_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[WorktreeConfig, ConfigShowView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(ConfigShowFormatter().to_rich(case.data))
        view = case.view

        assert view.config_path.as_posix() in rendered
        assert view.status in rendered
        assert view.config.project.name in rendered
        if view.config.agent.model is not None:
            assert view.config.agent.model in rendered
