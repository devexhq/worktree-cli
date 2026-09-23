"""Tier 2 presentation contract tests for ConfigShowFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.harness.formatter import (
    FormatterCase,
    assert_json_payload_matches_published_shape,
    assert_rich_render_shows_every_view_value,
    assert_transform_derives_expected_view,
)
from worktree.cli.ui.formatters.config import ConfigShowFormatter, ConfigShowView
from worktree.core.config.loader import resolve_config_path
from worktree.core.config.models import (
    AgentConfig,
    ConcurrencyConfig,
    DoctorConfig,
    HistoryConfig,
    ProjectConfig,
    PruneConfig,
    SandboxConfig,
    TelemetryConfig,
    WorktreeConfig,
)

RESOLVED_CONFIG_PATH = resolve_config_path()


def _make_config(name: str = "test-show-app", model: str | None = None) -> WorktreeConfig:
    return WorktreeConfig(
        version=1,
        project=ProjectConfig(name=name, initialized_at=None),
        sandbox=SandboxConfig(
            base_ref="HEAD",
            max_active_sandboxes=3,
            default_timeout_seconds=900,
        ),
        agent=AgentConfig(
            provider="local",
            model=model,
            endpoint=None,
            temperature=0.2,
            max_tokens=4096,
        ),
        history=HistoryConfig(
            save_attempt_logs=True,
            save_agent_payloads=True,
            save_final_diff=True,
            max_sessions=1000,
        ),
        doctor=DoctorConfig(
            check_git=True,
            check_paths_writable=True,
            check_config_schema=True,
            check_stale_worktrees=True,
            check_required_binaries=True,
        ),
        prune=PruneConfig(
            remove_stale_worktrees=True,
            remove_orphaned_sandboxes=True,
            remove_expired_artifacts=False,
            artifact_ttl_days=30,
        ),
        telemetry=TelemetryConfig(enabled=False),
        concurrency=ConcurrencyConfig(lock_timeout_seconds=30.0),
    )


DEFAULT_CONFIG = _make_config("test-show-app", "gemini-2.5-pro")
CUSTOM_CONFIG = _make_config("custom-project")

DEFAULT_CONFIG_CASE = FormatterCase(
    data=DEFAULT_CONFIG,
    view=ConfigShowView(
        config_path=RESOLVED_CONFIG_PATH,
        status="valid",
        config=DEFAULT_CONFIG,
    ),
    render_expectations=[RESOLVED_CONFIG_PATH.as_posix(), "valid", "test-show-app", "gemini-2.5-pro"],
)

CUSTOM_CONFIG_CASE = FormatterCase(
    data=CUSTOM_CONFIG,
    view=ConfigShowView(
        config_path=RESOLVED_CONFIG_PATH,
        status="valid",
        config=CUSTOM_CONFIG,
    ),
    render_expectations=[RESOLVED_CONFIG_PATH.as_posix(), "valid", "custom-project"],
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
                "ignore_global_root_error": False,
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
                "ignore_global_root_error": False,
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
        assert_transform_derives_expected_view(ConfigShowFormatter, case.data, case.view)

    @pytest.mark.parametrize(("case", "expected_payload"), SHOW_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WorktreeConfig, ConfigShowView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert_json_payload_matches_published_shape(ConfigShowFormatter, case.data, expected_payload)

    @pytest.mark.parametrize("case", SHOW_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[WorktreeConfig, ConfigShowView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        assert_rich_render_shows_every_view_value(ConfigShowFormatter, case.data, case.render_expectations)
