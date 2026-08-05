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
        assert "Config updated: agent.model = qwen2.5-coder" in out
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

    def test_set_after_init(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "set", "agent.model", "qwen2.5-coder"])
        assert result.exit_code == 0
        assert "Config updated: agent.model = qwen2.5-coder" in result.stdout
        config_path = git_repo / ".worktree" / "config.json"
        assert _read_config(config_path)["agent"]["model"] == "qwen2.5-coder"

    def test_set_creates_nested_path(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0

        result = runner.invoke(
            app, ["config", "set", "custom.toolchain.timeout", "120"]
        )
        assert result.exit_code == 0
        assert "Config updated: custom.toolchain.timeout = 120" in result.stdout
        data = _read_config(git_repo / ".worktree" / "config.json")
        assert data["custom"]["toolchain"]["timeout"] == "120"

    def test_set_type_collision(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        assert runner.invoke(app, ["init"]).exit_code == 0
        config_path = git_repo / ".worktree" / "config.json"
        data = _read_config(config_path)
        data["agents"] = {"ollama": "qwen2.5-coder"}
        config_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

        first = runner.invoke(app, ["config", "set", "agents.ollama", "qwen2.5-coder"])
        assert first.exit_code == 0

        second = runner.invoke(app, ["config", "set", "agents.ollama.port", "11434"])
        assert second.exit_code == 1
        combined = second.stdout + second.stderr
        assert "Config Error" in combined
        assert "agents.ollama.port" in combined
        assert "scalar" in combined
        assert _read_config(config_path)["agents"]["ollama"] == "qwen2.5-coder"

    def test_set_missing_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
