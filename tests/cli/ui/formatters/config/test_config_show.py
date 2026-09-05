"""Tier 2 presentation contract tests for ConfigShowFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.config.config_show import ConfigShowFormatter
from worktree.core.config.models import AgentConfig, ProjectConfig, WorktreeConfig


class ConfigShowFormatterTests:
    """Tests for ConfigShowFormatter."""

    def test_to_rich_renders_project_and_agent_config(self) -> None:
        formatter = ConfigShowFormatter()
        config = WorktreeConfig(
            version=1,
            project=ProjectConfig(name="test-show-app"),
            agent=AgentConfig(model="gemini-2.5-pro"),
        )
        rendered = render_rich(formatter.to_rich(config))
        assert "test-show-app" in rendered
        assert "gemini-2.5-pro" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = ConfigShowFormatter()
        config = WorktreeConfig(
            version=1,
            project=ProjectConfig(name="test-show-app"),
            agent=AgentConfig(model="gemini-2.5-pro"),
        )
        dumped = formatter.to_json_serializable(config)
        assert dumped == {
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
        }
