"""Dual-tier matrix tests for wt config validate."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app
from worktree.cli.config.commands.config_validate import config_validate_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.validate import (
    ConfigValidationStatus,
)
from worktree.core.db.db import WorktreeDb


class ConfigValidateRootTests:
    """Direct handler unit tests for config_validate_command."""

    def test_config_validate_clean_returns_valid(self, isolated_workspace: Path) -> None:
        """Handler returns VALID ConfigValidationResult for clean config."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_validate_command(context)

        assert result.status == ConfigValidationStatus.VALID
        assert result.config_path == config_path
        assert result.config == WorktreeConfig.model_validate(payload)
        assert result.raw == payload
        assert result.warnings == []
        assert result.errors == []
        assert result.fixes == []

    def test_config_validate_with_warnings_returns_valid_status(self, isolated_workspace: Path) -> None:
        """Handler returns VALID status with warnings for non-local provider missing model."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        payload["agent"]["provider"] = "openai"
        payload["agent"]["model"] = None
        Filesystem.atomic_write_json(config_path, payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_validate_command(context)

        assert result.status == ConfigValidationStatus.VALID
        assert result.config_path == config_path
        assert result.config == WorktreeConfig.model_validate(payload)
        assert result.raw == payload
        assert result.warnings == [
            "agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING)."
        ]
        assert result.errors == []
        assert result.fixes == ["Set agent.model or use provider=local"]

    def test_config_validate_error_returns_invalid_status(self, isolated_workspace: Path) -> None:
        """Handler returns INVALID status for schema-invalid config."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        invalid_payload = {"version": 1}
        Filesystem.atomic_write_json(config_path, invalid_payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_validate_command(context)

        assert result.status == ConfigValidationStatus.INVALID
        assert result.config_path == config_path
        assert result.config is None
        assert result.raw == invalid_payload
        assert result.errors == [
            "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- (root): 'project' is a required property"
        ]
        assert result.warnings == []
        assert result.fixes == [
            "Run `wt config validate` for details",
            "Or `wt init --repair` to insert missing keys without overwriting values",
        ]


class ConfigValidateCliIntegrationTests:
    """Typer runner integration tests for wt config validate."""

    def test_config_validate_cli_clean_exits_zero(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config validate prints valid status on clean config."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "validate"])

        assert res.exit_code == 0
        assert "Status: valid" in res.stdout
        assert "Config is valid." in res.stdout

    def test_config_validate_cli_warnings_exits_zero(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config validate prints warnings for non-blocking issues."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        payload["agent"]["provider"] = "openai"
        payload["agent"]["model"] = None
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "validate"])

        assert res.exit_code == 0
        assert "Status: valid with warnings" in res.stdout
        assert "Warnings:" in res.stdout

    def test_config_validate_cli_schema_error_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config validate exits with error panel on schema violation."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        invalid_payload = {"version": 1}
        Filesystem.atomic_write_json(config_path, invalid_payload)

        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "validate"])

        assert res.exit_code == 1
        assert "Config Validation Failed" in res.stdout
        assert "CONFIG_SCHEMA_INVALID" in res.stdout

    def test_config_validate_cli_format_json_emits_event(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config validate --format json emits NDJSON ConfigValidationResult event."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "config", "validate", "--format", "json"],
        )

        assert res.exit_code == 0
        raw_payload = json.loads(config_path.read_text())
        assert json.loads(res.stdout) == {
            "event_type": "ConfigValidationResult",
            "payload": {
                "status": "valid",
                "config_path": str(config_path),
                "status_label": "valid",
                "raw": raw_payload,
                "config": raw_payload,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
