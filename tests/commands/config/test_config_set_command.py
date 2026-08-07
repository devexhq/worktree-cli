"""Tests for `wt config set`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import typer
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.config.command import config_set_command
from getworktree.core.config.generator import generate_default_config

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


def _write_default_config(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    gen = generate_default_config(config_path, project_name=repo.name)
    assert gen.ok
    return config_path


def _read_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


class ConfigSetCommandTests:
    """Direct command tests for config set."""

    def test_success_updates_nested_key(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            config_set_command("agent.model", "qwen2.5-coder", cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        assert "Config updated: agent.model = qwen2.5-coder (str)" in out
        assert _read_config(config_path)["agent"]["model"] == "qwen2.5-coder"

    def test_type_collision_exits_nonzero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)
        data = _read_config(config_path)
        data["agents"] = {"ollama": "qwen2.5-coder"}
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        original = config_path.read_text(encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            config_set_command("agents.ollama.port", "11434", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Config Error" in out
        assert "agents.ollama.port" in out
        assert "scalar" in out
        assert config_path.read_text(encoding="utf-8") == original

    def test_missing_config_exits_nonzero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            config_set_command("agent.model", "x", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "CONFIG_NOT_FOUND" in out or "not found" in out.lower()


class ConfigSetCliTests:
    """CLI wiring tests for `wt config set`."""

    def test_set_after_init(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 0
        assert "Config updated: agent.model = qwen2.5-coder (str)" in result.stdout
        config_path = git_repo / ".worktree" / "config.json"
        assert _read_config(config_path)["agent"]["model"] == "qwen2.5-coder"

    def test_set_typed_values(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0

        res_bool = runner.invoke(app, ["config", "set", "sandbox.auto_clean", "false"])
        assert res_bool.exit_code == 0
        assert "Config updated: sandbox.auto_clean = false (bool)" in res_bool.stdout

        res_float = runner.invoke(app, ["config", "set", "agent.temperature", "0.7"])
        assert res_float.exit_code == 0
        assert "Config updated: agent.temperature = 0.7 (float)" in res_float.stdout

        res_int = runner.invoke(app, ["config", "set", "sandbox.max_active_sandboxes", "5"])
        assert res_int.exit_code == 0
        assert "Config updated: sandbox.max_active_sandboxes = 5 (int)" in res_int.stdout

        res_quoted = runner.invoke(app, ["config", "set", "agent.model", '"qwen2.5"'])
        assert res_quoted.exit_code == 0
        assert "Config updated: agent.model = qwen2.5 (str)" in res_quoted.stdout

        data = _read_config(git_repo / ".worktree" / "config.json")
        assert data["sandbox"]["auto_clean"] is False
        assert data["agent"]["temperature"] == 0.7
        assert data["sandbox"]["max_active_sandboxes"] == 5
        assert data["agent"]["model"] == "qwen2.5"

    def test_set_invalid_schema_key_exits_nonzero(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0

        result = runner.invoke(app, ["config", "set", "sandboxes.max_active_sandboxes", "3"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "CONFIG_SCHEMA_INVALID" in combined
        assert "sandboxes" in combined

    def test_set_type_collision(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0
        config_path = git_repo / ".worktree" / "config.json"
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
        assert "agent.model" in combined
        assert "scalar" in combined
        assert _read_config(config_path)["agent"] == "scalar-value"

    def test_set_missing_config(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["config", "set", "agent.model", "x"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "CONFIG_NOT_FOUND" in combined or "not found" in combined.lower()

    def test_help_lists_config_set(self) -> None:
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == 0

        set_cmd = get_command(app).get_command(None, "config").get_command(None, "set")
        assert set_cmd.help == "Set a configuration value by key or nested dot-path."
        params = {p.name for p in set_cmd.params}
        assert "key" in params
        assert "value" in params

    def test_set_write_failure_displays_error_panel(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0

        def mock_write_json(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("getworktree.core.config.mutate.atomic_write_json", mock_write_json)

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "CONFIG_WRITE_FAILED" in combined
        assert "Permission denied" in combined
