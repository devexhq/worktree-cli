"""Tests for `wt config set`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_cli_context
from worktree.cli import app
from worktree.cli.config.commands.config_set import config_set_command

runner = CliRunner()


def _read_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


class ConfigSetCommandTests:
    """Direct command tests for config set."""

    def test_success_updates_nested_key(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_set_command(ctx, "agent.model", "qwen2.5-coder")
        assert outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Config updated: agent.model = qwen2.5-coder (str)" in out
        assert _read_config(config_path)["agent"]["model"] == "qwen2.5-coder"

    def test_type_collision_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.init_repo()
        data = _read_config(config_path)
        data["agents"] = {"ollama": "qwen2.5-coder"}
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        original = config_path.read_text(encoding="utf-8")

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_set_command(ctx, "agents.ollama.port", "11434")
        assert not outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Config Error" in out
        assert "agents.ollama.port" in out
        assert "scalar" in out
        assert config_path.read_text(encoding="utf-8") == original

    def test_missing_config_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_set_command(ctx, "agent.model", "x")
        assert not outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "CONFIG_NOT_FOUND" in out or "not found" in out.lower()


class ConfigSetCliTests:
    """CLI wiring tests for `wt config set`."""

    def test_set_after_init(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 0
        assert "Config updated: agent.model = qwen2.5-coder (str)" in result.stdout
        config_path = git_fs.base_path / ".worktree" / "config.json"
        assert _read_config(config_path)["agent"]["model"] == "qwen2.5-coder"

    def test_set_typed_values(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        assert runner.invoke(app, ["init"]).exit_code == 0

        res_bool = runner.invoke(app, ["config", "set", "telemetry.enabled", "true"])
        assert res_bool.exit_code == 0
        assert "Config updated: telemetry.enabled = true (bool)" in res_bool.stdout

        res_float = runner.invoke(app, ["config", "set", "agent.temperature", "0.7"])
        assert res_float.exit_code == 0
        assert "Config updated: agent.temperature = 0.7 (float)" in res_float.stdout

        res_int = runner.invoke(app, ["config", "set", "sandbox.max_active_sandboxes", "5"])
        assert res_int.exit_code == 0
        assert "Config updated: sandbox.max_active_sandboxes = 5 (int)" in res_int.stdout

        res_quoted = runner.invoke(app, ["config", "set", "agent.model", '"qwen2.5"'])
        assert res_quoted.exit_code == 0
        assert "Config updated: agent.model = qwen2.5 (str)" in res_quoted.stdout

        data = _read_config(git_fs.base_path / ".worktree" / "config.json")
        assert data["telemetry"]["enabled"] is True
        assert data["agent"]["temperature"] == 0.7
        assert data["sandbox"]["max_active_sandboxes"] == 5
        assert data["agent"]["model"] == "qwen2.5"

    def test_set_invalid_schema_key_exits_nonzero(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        assert runner.invoke(app, ["init"]).exit_code == 0

        result = runner.invoke(app, ["config", "set", "sandboxes.max_active_sandboxes", "3"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "CONFIG_SCHEMA_INVALID" in combined
        assert "sandboxes" in combined

    def test_set_type_collision(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        assert runner.invoke(app, ["init"]).exit_code == 0
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = _read_config(config_path)
        data["agent"] = "scalar-value"
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert _read_config(config_path)["agent"] == "scalar-value"

    def test_set_missing_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["config", "set", "agent.model", "x"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "not found" in combined

    def test_help_lists_config_set(self) -> None:
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == 0

        set_cmd = get_command(app).get_command(None, "config").get_command(None, "set")
        assert set_cmd.help == "Set a configuration value by key or nested dot-path."
        params = {p.name for p in set_cmd.params}
        assert "key" in params
        assert "value" in params

    def test_set_write_failure_displays_error_panel(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        assert runner.invoke(app, ["init"]).exit_code == 0

        def mock_write_json(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("worktree.core.config.mutate.atomic_write_json", mock_write_json)

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "CONFIG_WRITE_FAILED" in combined
        assert "Permission denied" in combined
