"""Dual-tier matrix tests for wt config show."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app
from worktree.cli.config.commands.config_show import config_show_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import WorktreeConfig
from worktree.core.db.db import WorktreeDb


class ConfigShowRootTests:
    """Direct handler unit tests for config_show_command."""

    def test_config_show_returns_effective_config(self, isolated_workspace: Path) -> None:
        """Handler returns ConfigLoadResult with loaded configuration."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_show_command(context)

        assert result.status == ConfigLoadStatus.OK
        assert result.config_path == config_path
        assert result.config == WorktreeConfig.model_validate(payload)
        assert result.raw == payload
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    def test_config_show_missing_config_returns_not_found(self, isolated_workspace: Path) -> None:
        """Handler returns NOT_FOUND status when config.json is missing."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_show_command(context)

        assert result.status == ConfigLoadStatus.NOT_FOUND
        assert result.config_path == config_path
        assert result.config is None
        assert result.raw is None
        assert result.errors == [f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND)."]
        assert result.fixes == ["Run `wt init` to create `.worktree/config.json`"]
        assert result.warnings == []


class ConfigShowCliIntegrationTests:
    """Typer runner integration tests for wt config show."""

    def test_config_show_cli_renders_effective_config_terminal(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """wt config show prints header and effective JSON."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "show"])

        assert res.exit_code == 0
        assert "Config: " in res.stdout
        assert "Status: valid" in res.stdout
        assert '"version": 1' in res.stdout

    def test_config_show_cli_renders_json(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config show --format json emits NDJSON ConfigLoadResult."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "show", "--format", "json"])

        assert res.exit_code == 0
        raw_payload = json.loads(config_path.read_text())
        assert json.loads(res.stdout) == {
            "event_type": "ConfigLoadResult",
            "payload": {
                "status": "ok",
                "config_path": str(config_path),
                "raw": raw_payload,
                "config": raw_payload,
                "error_code": None,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }

    def test_config_show_cli_missing_config_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config show exits on missing config with error panel."""
        res = cli_runner.invoke(app, ["-p", str(isolated_workspace), "config", "show"])

        assert res.exit_code == 1
        assert "Config Error" in res.stdout
        assert "CONFIG_NOT_FOUND" in res.stdout
