"""Dual-tier matrix tests for config CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.assertions import assert_model_equal
from worktree.cli import app
from worktree.cli.config.commands.config_set import config_set_command
from worktree.cli.config.commands.config_show import config_show_command
from worktree.cli.config.commands.config_validate import config_validate_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.mutate import ConfigSetResult, ConfigSetStatus
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)
from worktree.core.db.facade import WorktreeDb

pytestmark = pytest.mark.cli


# --------------------------------------------------------------------------- #
# Config Show Tests                                                           #
# --------------------------------------------------------------------------- #


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

        assert_model_equal(
            result,
            ConfigLoadResult(
                status=ConfigLoadStatus.OK,
                config_path=config_path,
                config=WorktreeConfig.model_validate(payload),
                raw=payload,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_config_show_missing_config_returns_not_found(self, isolated_workspace: Path) -> None:
        """Handler returns NOT_FOUND status when config.json is missing."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_show_command(context)

        assert_model_equal(
            result,
            ConfigLoadResult(
                status=ConfigLoadStatus.NOT_FOUND,
                config_path=config_path,
                config=None,
                raw=None,
                errors=[f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND)."],
                fixes=["Run `wt init` to create `.worktree/config.json`"],
                warnings=[],
            ),
        )


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


# --------------------------------------------------------------------------- #
# Config Set Tests                                                            #
# --------------------------------------------------------------------------- #


class ConfigSetRootTests:
    """Direct handler unit tests for config_set_command."""

    def test_config_set_updates_scalar_value_returns_ok(self, isolated_workspace: Path) -> None:
        """Handler returns OK ConfigSetResult and mutates config atomically."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_set_command(context, "agent.model", "qwen2.5-coder")

        assert_model_equal(
            result,
            ConfigSetResult(
                status=ConfigSetStatus.OK,
                config_path=config_path,
                key="agent.model",
                value="qwen2.5-coder",
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
        assert json.loads(config_path.read_text())["agent"]["model"] == "qwen2.5-coder"

    def test_config_set_schema_violation_returns_error(self, isolated_workspace: Path) -> None:
        """Handler returns SCHEMA_INVALID ConfigSetResult on bad schema key."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_set_command(context, "sandboxes.max_active_sandboxes", "3")

        assert_model_equal(
            result,
            ConfigSetResult(
                status=ConfigSetStatus.SCHEMA_INVALID,
                config_path=config_path,
                key="sandboxes.max_active_sandboxes",
                value=3,
                errors=[
                    "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- (root): Additional properties are not allowed ('sandboxes' was unexpected)"
                ],
                fixes=[
                    "Run `wt config validate` for details",
                    "Or `wt init --repair` to insert missing keys without overwriting values",
                ],
                warnings=[],
            ),
        )
        assert json.loads(config_path.read_text()) == payload


class ConfigSetCliIntegrationTests:
    """Typer runner integration tests for wt config set."""

    def test_config_set_cli_mutates_value_and_exits_zero(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config set updates value and displays confirmation."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "config", "set", "agent.model", "qwen2.5-coder"],
        )

        assert res.exit_code == 0
        assert "Config updated: agent.model" in res.stdout
        assert json.loads(config_path.read_text())["agent"]["model"] == "qwen2.5-coder"

    def test_config_set_cli_stores_boolean_true_from_string(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """wt config set converts "true" to boolean True and stores True in config.json."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "config", "set", "telemetry.enabled", "true"],
        )

        assert res.exit_code == 0
        assert "(bool)" in res.stdout
        assert json.loads(config_path.read_text())["telemetry"]["enabled"] is True

    def test_config_set_cli_schema_violation_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config set exits with error panel on schema violation."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(
            app,
            [
                "-p",
                str(isolated_workspace),
                "config",
                "set",
                "--",
                "sandbox.max_active_sandboxes",
                "-1",
            ],
        )

        assert res.exit_code == 1
        assert "Config Error" in res.stdout
        assert "CONFIG_SCHEMA_INVALID" in res.stdout

    def test_config_set_cli_format_json_emits_event(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt config set --format json emits NDJSON ConfigSetResult event."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        payload = build_default_config("demo-workspace")
        Filesystem.atomic_write_json(config_path, payload)

        res = cli_runner.invoke(
            app,
            [
                "-p",
                str(isolated_workspace),
                "config",
                "set",
                "agent.model",
                "qwen2.5-coder",
                "--format",
                "json",
            ],
        )

        assert res.exit_code == 0
        assert json.loads(res.stdout) == {
            "event_type": "ConfigSetResult",
            "payload": {
                "status": "ok",
                "config_path": str(config_path),
                "key": "agent.model",
                "value": "qwen2.5-coder",
                "value_str": "qwen2.5-coder",
                "value_type": "str",
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }


# --------------------------------------------------------------------------- #
# Config Validate Tests                                                       #
# --------------------------------------------------------------------------- #


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

        assert_model_equal(
            result,
            ConfigValidationResult(
                status=ConfigValidationStatus.VALID,
                config_path=config_path,
                config=WorktreeConfig.model_validate(payload),
                raw=payload,
                warnings=[],
                errors=[],
                fixes=[],
            ),
        )

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

        assert_model_equal(
            result,
            ConfigValidationResult(
                status=ConfigValidationStatus.VALID,
                config_path=config_path,
                config=WorktreeConfig.model_validate(payload),
                raw=payload,
                warnings=[
                    "agent.provider is not 'local' but agent.model is missing (CONFIG_WARN_AGENT_MODEL_MISSING)."
                ],
                errors=[],
                fixes=["Set agent.model or use provider=local"],
            ),
        )

    def test_config_validate_error_returns_invalid_status(self, isolated_workspace: Path) -> None:
        """Handler returns INVALID status for schema-invalid config."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        invalid_payload = {"version": 1}
        Filesystem.atomic_write_json(config_path, invalid_payload)

        fs = Filesystem.configure(isolated_workspace)
        context = CliContext(cwd=isolated_workspace, db=WorktreeDb(path=isolated_workspace), fs=fs)
        result = config_validate_command(context)

        assert_model_equal(
            result,
            ConfigValidationResult(
                status=ConfigValidationStatus.INVALID,
                config_path=config_path,
                config=None,
                raw=invalid_payload,
                errors=[
                    "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- (root): 'project' is a required property\n- (root): 'paths' is a required property\n- (root): 'sandbox' is a required property\n- (root): 'agent' is a required property\n- (root): 'history' is a required property\n- (root): 'doctor' is a required property\n- (root): 'prune' is a required property\n- (root): 'telemetry' is a required property\n- (root): 'concurrency' is a required property"
                ],
                warnings=[],
                fixes=[
                    "Run `wt config validate` for details",
                    "Or `wt init --repair` to insert missing keys without overwriting values",
                ],
            ),
        )


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
