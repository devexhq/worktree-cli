"""Tests for `wt config validate`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.config.command import config_validate_command
from getworktree.core.config.generator import generate_default_config
from getworktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)

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


def _write_config(config_path: Path, data: dict) -> None:
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _assert_success_stdout(
    stdout: str,
    *,
    config_path: Path,
    with_warnings: bool,
) -> None:
    status = "valid with warnings" if with_warnings else "valid"
    lines = stdout.splitlines()
    assert lines[0] == f"Config: {config_path.resolve().as_posix()}"
    assert lines[1] == f"Status: {status}"
    assert lines[2] == ""
    assert lines[-1] == "Config is valid."
    if with_warnings:
        assert "Warnings:" in lines
        warning_idx = lines.index("Warnings:")
        assert warning_idx > 2
        assert any(line.startswith("- ") for line in lines[warning_idx + 1 :])
    else:
        assert "Warnings:" not in lines
    assert "Config Validation Failed" not in stdout


def _assert_failure_output(stdout: str, stderr: str = "") -> str:
    combined = stdout + stderr
    assert "Config Validation Failed" in combined
    assert "Status: valid" not in stdout
    assert "Config is valid." not in stdout
    assert not any(
        line.startswith("Config: ") and line.endswith("config.json")
        for line in stdout.splitlines()
    )
    return combined


class ConfigValidateCommandTests:
    """Direct command tests for config validate."""

    def test_valid_config_exits_zero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0
        _assert_success_stdout(
            capsys.readouterr().out,
            config_path=config_path,
            with_warnings=False,
        )

    def test_valid_with_warnings_exits_zero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)
        data = _read_config(config_path)
        data["agent"]["provider"] = "openai"
        data["agent"]["model"] = None
        _write_config(config_path, data)

        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        _assert_success_stdout(out, config_path=config_path, with_warnings=True)
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in out
        # Multi-line engine messages keep continuation indented by two spaces.
        assert any(line.startswith("  ") for line in out.splitlines())

    def test_missing_config_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "CONFIG_NOT_FOUND" in combined or "not found" in combined.lower()

    def test_schema_invalid_exits_one(
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
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "schema" in combined.lower() or "CONFIG_SCHEMA_INVALID" in combined

    def test_semantic_invalid_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)
        data = _read_config(config_path)
        data["loop"]["default_max_attempts"] = 50
        data["loop"]["max_attempts_hard_limit"] = 20
        _write_config(config_path, data)

        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "CONFIG_SEMANTIC_MAX_ATTEMPTS" in combined

    def test_malformed_json_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{not-json\n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "CONFIG_MALFORMED_JSON" in combined or "json" in combined.lower()

    def test_path_is_directory_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.mkdir(parents=True)

        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "CONFIG_PATH_IS_DIRECTORY" in combined or "directory" in combined.lower()

    def test_empty_errors_uses_fallback_body(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        fake = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=(git_repo / ".worktree" / "config.json").resolve(),
            errors=[],
            warnings=[],
        )
        with patch(
            "getworktree.commands.config.command.validate_config_result",
            return_value=fake,
        ):
            with pytest.raises(typer.Exit) as exc_info:
                config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_output(capsys.readouterr().out)
        assert "Configuration validation failed." in combined

    def test_invalid_with_warnings_prints_warnings_after_panel(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        fake = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=(git_repo / ".worktree" / "config.json").resolve(),
            errors=["semantic boom (CONFIG_SEMANTIC_MAX_ATTEMPTS)."],
            warnings=[
                "agent.provider is not 'local' but agent.model is missing "
                "(CONFIG_WARN_AGENT_MODEL_MISSING).\n"
                "Fix:\n"
                "- set agent.model or use provider=local"
            ],
        )
        with patch(
            "getworktree.commands.config.command.validate_config_result",
            return_value=fake,
        ):
            with pytest.raises(typer.Exit) as exc_info:
                config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        combined = _assert_failure_output(out)
        assert "CONFIG_SEMANTIC_MAX_ATTEMPTS" in combined
        assert "Warnings:" in out
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in out
        # Warnings section appears after the panel title in stdout.
        assert out.index("Config Validation Failed") < out.index("Warnings:")

    def test_does_not_create_config_when_missing(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        assert not config_path.exists()
        with pytest.raises(typer.Exit) as exc_info:
            config_validate_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        assert not config_path.exists()
        _assert_failure_output(capsys.readouterr().out)


class ConfigValidateCliTests:
    """CLI wiring tests for `wt config validate`."""

    def test_validate_after_init(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        init = runner.invoke(app, ["init"])
        assert init.exit_code == 0

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        config_path = git_repo / ".worktree" / "config.json"
        _assert_success_stdout(
            result.stdout,
            config_path=config_path,
            with_warnings=False,
        )

    def test_validate_with_warnings(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)
        data = _read_config(config_path)
        data["agent"]["provider"] = "openai"
        data["agent"]["model"] = None
        data["sandbox"]["max_active_sandboxes"] = 12
        _write_config(config_path, data)

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        _assert_success_stdout(
            result.stdout,
            config_path=config_path,
            with_warnings=True,
        )
        assert "CONFIG_WARN_AGENT_MODEL_MISSING" in result.stdout
        assert "CONFIG_WARN_SANDBOX_LIMIT" in result.stdout

    def test_validate_missing_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        combined = _assert_failure_output(result.stdout, result.stderr)
        assert "CONFIG_NOT_FOUND" in combined or "not found" in combined.lower()
        assert "wt init" in combined

    def test_validate_schema_invalid(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        combined = _assert_failure_output(result.stdout, result.stderr)
        assert "schema" in combined.lower() or "CONFIG_SCHEMA_INVALID" in combined

    def test_validate_semantic_invalid(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = _write_default_config(git_repo)
        data = _read_config(config_path)
        data["loop"]["default_max_attempts"] = 50
        data["loop"]["max_attempts_hard_limit"] = 20
        _write_config(config_path, data)

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        combined = _assert_failure_output(result.stdout, result.stderr)
        assert "CONFIG_SEMANTIC_MAX_ATTEMPTS" in combined

    def test_help_lists_config_validate(self) -> None:
        root = runner.invoke(app, ["--help"])
        assert root.exit_code == 0
        assert "config" in root.stdout

        cfg = runner.invoke(app, ["config", "--help"])
        assert cfg.exit_code == 0

        root_cmd = get_command(app)
        config_cmd = root_cmd.get_command(None, "config")
        assert (
            config_cmd.help == "Inspect, update, and validate Worktree configuration."
        )
        assert "show" in config_cmd.list_commands(None)
        assert "set" in config_cmd.list_commands(None)
        assert "validate" in config_cmd.list_commands(None)

        validate_cmd = config_cmd.get_command(None, "validate")
        assert (
            validate_cmd.help
            == "Validate .worktree/config.json against the V1 schema and semantic rules."
        )
