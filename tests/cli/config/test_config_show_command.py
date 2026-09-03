"""Tests for `wt config show`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_cli_context
from worktree.cli import app
from worktree.cli.config.commands.config_show import config_show_command

runner = CliRunner()


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
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_show_command(ctx)
        assert outcome.ok
        ctx.output.print()
        header, body = _split_show_stdout(capsys.readouterr().out)
        _assert_success_header(header, config_path)
        data = json.loads(body)
        assert data["version"] == 1
        assert data["project"]["name"] == git_fs.base_path.name
        assert data["paths"]["root_dir"] == ".worktree"

    def test_missing_config_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_show_command(ctx)
        assert not outcome.ok
        ctx.output.print()
        _assert_no_success_header(capsys.readouterr().out)

    def test_schema_invalid_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_show_command(ctx)
        assert not outcome.ok
        ctx.output.print()
        _assert_no_success_header(capsys.readouterr().out)

    def test_show_output_format_json(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = config_show_command(ctx, output_format="json")
        assert outcome.ok
        out = capsys.readouterr().out
        lines = [line for line in out.strip().split("\n") if line]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigLoadResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["config"]["version"] == 1
        assert payload["payload"]["config"]["project"]["name"] == git_fs.base_path.name


class ConfigShowCliTests:
    """CLI wiring tests for `wt config show`."""

    def test_show_after_init(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        config_path = git_fs.base_path / ".worktree" / "config.json"
        header, body = _split_show_stdout(result.stdout)
        _assert_success_header(header, config_path)
        data = json.loads(body)
        assert data["version"] == 1
        assert data["project"]["name"] == git_fs.base_path.name
        assert "paths" in data
        assert "telemetry" in data
        assert data["agent"]["provider"] == "local"

    def test_show_cli_json_format(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "show", "--format", "json"])
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigLoadResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["config"]["version"] == 1
        assert payload["payload"]["config"]["project"]["name"] == git_fs.base_path.name

    def test_show_missing_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "not found" in combined
        _assert_no_success_header(result.stdout)
        # Must not look like a successful effective JSON object dump.
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_show_schema_invalid(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "Config Error" in combined
        assert "CONFIG_SCHEMA_INVALID" in combined
        _assert_no_success_header(result.stdout)
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_help_lists_config_show(self) -> None:
        root_cmd = typer.main.get_command(app)
        assert "config" in root_cmd.list_commands(None)
        config_cmd = root_cmd.get_command(None, "config")
        assert config_cmd is not None
        assert "show" in config_cmd.list_commands(None)

        show_cmd = config_cmd.get_command(None, "show")
        assert show_cmd is not None
        opts: set[str] = set()
        for param in show_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--format" in opts
