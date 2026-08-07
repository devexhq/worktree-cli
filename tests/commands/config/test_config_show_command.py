"""Tests for `wt config show`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.config.command import config_show_command
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


def _split_show_stdout(stdout: str) -> tuple[str, str]:
    """Split success stdout into header block and JSON body."""
    header, sep, body = stdout.partition("\n\n")
    assert sep == "\n\n", "success stdout must contain a blank line after header"
    return header, body


def _assert_success_header(header: str, config_path: Path) -> None:
    lines = header.splitlines()
    assert lines == [
        f"Config: {config_path.resolve().as_posix()}",
        "Status: valid",
    ]


def _assert_no_success_header(stdout: str) -> None:
    assert "Status: valid" not in stdout
    assert not any(line.startswith("Config: ") and line.endswith("config.json") for line in stdout.splitlines())


class ConfigShowCommandTests:
    """Direct command tests for config show."""

    def test_success_prints_header_and_parseable_effective_json(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        gen = generate_default_config(config_path, project_name=git_repo.name)
        assert gen.ok

        config_show_command(cwd=git_repo)
        header, body = _split_show_stdout(capsys.readouterr().out)
        _assert_success_header(header, config_path)
        data = json.loads(body)
        assert data["version"] == 1
        assert data["project"]["name"] == git_repo.name
        assert data["paths"]["root_dir"] == ".worktree"

    def test_missing_config_exits_nonzero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            config_show_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        _assert_no_success_header(capsys.readouterr().out)

    def test_schema_invalid_exits_nonzero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            config_show_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        _assert_no_success_header(capsys.readouterr().out)


class ConfigShowCliTests:
    """CLI wiring tests for `wt config show`."""

    def test_show_after_init(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        config_path = git_repo / ".worktree" / "config.json"
        header, body = _split_show_stdout(result.stdout)
        _assert_success_header(header, config_path)
        data = json.loads(body)
        assert data["version"] == 1
        assert data["project"]["name"] == git_repo.name
        assert "paths" in data
        assert "telemetry" in data
        assert data["workflow"]["default_max_attempts"] == 5

    def test_show_missing_config(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "CONFIG_NOT_FOUND" in combined or "not found" in combined.lower()
        _assert_no_success_header(result.stdout)
        # Must not look like a successful effective JSON object dump.
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_show_schema_invalid(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "schema" in combined.lower() or "CONFIG_SCHEMA_INVALID" in combined
        _assert_no_success_header(result.stdout)
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_help_lists_config_show(self) -> None:
        root = runner.invoke(app, ["--help"])
        assert root.exit_code == 0
        assert "config" in root.stdout

        cfg = runner.invoke(app, ["config", "--help"])
        assert cfg.exit_code == 0
        assert "show" in cfg.stdout
