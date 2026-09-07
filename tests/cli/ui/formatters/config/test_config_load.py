"""Tier 2 presentation contract tests for ConfigLoadFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.config.config_load import ConfigLoadFormatter
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import ProjectConfig, WorktreeConfig

_CONFIG_PATH = Path("/workspace/.worktree/config.json")

VALID_CONFIG = FormatterCase(
    data=ConfigLoadResult(
        status=ConfigLoadStatus.OK,
        config_path=_CONFIG_PATH,
        config=WorktreeConfig(version=1, project=ProjectConfig(name="test-project")),
    ),
    view=ConfigLoadResult(
        status=ConfigLoadStatus.OK,
        config_path=_CONFIG_PATH,
        config=WorktreeConfig(version=1, project=ProjectConfig(name="test-project")),
    ),
)

NOT_FOUND = FormatterCase(
    data=ConfigLoadResult(
        status=ConfigLoadStatus.NOT_FOUND,
        config_path=_CONFIG_PATH,
        errors=["Configuration file not found at '/workspace/.worktree/config.json' (CONFIG_NOT_FOUND)."],
        fixes=["Run `wt init` to initialize Worktree"],
    ),
    view=ConfigLoadResult(
        status=ConfigLoadStatus.NOT_FOUND,
        config_path=_CONFIG_PATH,
        errors=["Configuration file not found at '/workspace/.worktree/config.json' (CONFIG_NOT_FOUND)."],
        fixes=["Run `wt init` to initialize Worktree"],
    ),
)

CONFIG_LOAD_CASES = [
    pytest.param(VALID_CONFIG, id="valid_config"),
    pytest.param(NOT_FOUND, id="not_found"),
]

CONFIG_LOAD_PAYLOAD_CASES = [
    pytest.param(
        VALID_CONFIG,
        {
            "status": "ok",
            "config_path": "/workspace/.worktree/config.json",
            "raw": None,
            "config": {
                "version": 1,
                "project": {
                    "name": "test-project",
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
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="valid_config",
    ),
    pytest.param(
        NOT_FOUND,
        {
            "status": "not_found",
            "config_path": "/workspace/.worktree/config.json",
            "raw": None,
            "config": None,
            "warnings": [],
            "errors": ["Configuration file not found at '/workspace/.worktree/config.json' (CONFIG_NOT_FOUND)."],
            "fixes": ["Run `wt init` to initialize Worktree"],
        },
        id="not_found",
    ),
]


class ConfigLoadFormatterTests:
    """Tier 2 presentation contract tests for ConfigLoadFormatter."""

    @pytest.mark.parametrize("case", CONFIG_LOAD_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[ConfigLoadResult, ConfigLoadResult]) -> None:
        """Verify transform derives the identity view representation."""
        assert ConfigLoadFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), CONFIG_LOAD_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[ConfigLoadResult, ConfigLoadResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert ConfigLoadFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", CONFIG_LOAD_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[ConfigLoadResult, ConfigLoadResult]) -> None:
        """Verify non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(ConfigLoadFormatter().to_rich(case.data))
        view = case.view

        if view.ok and view.config is not None:
            assert view.config.project.name in rendered
            assert view.config_path.as_posix() in rendered
        else:
            for error in view.errors:
                assert error in rendered
            for fix in view.fixes:
                assert fix in rendered
