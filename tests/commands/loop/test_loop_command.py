"""Tests for the loop command."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

from getworktree.commands.loop.command import (
    format_error_payload,
    loop_command,
    run_command_in_sandbox,
)
from getworktree.commands.loop.models import ExecutionResult
from getworktree.core.config.generator import generate_default_config
from getworktree.core.git_sandbox import SandboxSession


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-b", "feature"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "f.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    wt = tmp_path / ".worktree"
    wt.mkdir()
    generate_default_config(wt / "config.json", tmp_path.name)
    return tmp_path


class RunCommandInSandboxTests:
    """Tests for sandbox command execution helper."""

    def test_success(self, tmp_path: Path) -> None:
        result = run_command_in_sandbox("true", tmp_path)
        assert result.passed
        assert result.returncode == 0

    def test_failure(self, tmp_path: Path) -> None:
        result = run_command_in_sandbox("false", tmp_path)
        assert not result.passed
        assert result.returncode != 0

    def test_timeout(self, tmp_path: Path) -> None:
        result = run_command_in_sandbox("sleep 2", tmp_path, timeout_seconds=1)
        assert not result.passed
        assert result.returncode == 124
        assert "timed out" in result.stderr.lower()


class FormatErrorPayloadTests:
    """Tests for diagnostic payload formatting."""

    def test_includes_command_and_session(self) -> None:
        result = ExecutionResult(
            command="pytest",
            returncode=1,
            stdout="",
            stderr="boom",
            passed=False,
        )
        payload = format_error_payload(result, "feature", "loop_abc")
        assert "loop_abc" in payload
        assert "feature" in payload
        assert "pytest" in payload
        assert "boom" in payload
        assert "LOOP FAILURE DIAGNOSTIC PAYLOAD" in payload


class LoopCommandTests:
    """Tests for loop_command orchestration."""

    def test_success_path_no_token_audit(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        session = SandboxSession(
            session_id="loop_test",
            target_branch="worktree/sandbox-loop_test",
            sandbox_path=git_repo,
            created_at="2020-01-01T00:00:00+00:00",
        )

        @contextmanager
        def fake_scope(**kwargs):
            yield session

        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(
            "getworktree.commands.loop.command.sandbox_scope",
            fake_scope,
        )
        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_command_in_sandbox",
            lambda *a, **k: ExecutionResult(
                command="true",
                returncode=0,
                stdout="",
                stderr="",
                passed=True,
            ),
        )
        record = MagicMock()
        monkeypatch.setattr(
            "getworktree.core.db.record_token_usage", record, raising=False
        )

        loop_command("true")
        out = capsys.readouterr().out
        assert "Execution passed" in out
        assert "Audited Session Spend" not in out
        assert "token" not in out.lower() or "token_audit" not in out.lower()
        record.assert_not_called()

    def test_failure_path_shows_payload(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        session = SandboxSession(
            session_id="loop_test",
            target_branch="worktree/sandbox-loop_test",
            sandbox_path=git_repo,
            created_at="2020-01-01T00:00:00+00:00",
        )

        @contextmanager
        def fake_scope(**kwargs):
            yield session

        monkeypatch.chdir(git_repo)
        monkeypatch.setattr(
            "getworktree.commands.loop.command.sandbox_scope",
            fake_scope,
        )
        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_command_in_sandbox",
            lambda *a, **k: ExecutionResult(
                command="false",
                returncode=1,
                stdout="",
                stderr="tests failed",
                passed=False,
            ),
        )

        loop_command("false")
        out = capsys.readouterr().out
        assert "failed" in out.lower()
        assert "LOOP FAILURE DIAGNOSTIC PAYLOAD" in out
        assert "Audited Session Spend" not in out

    def test_missing_config_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc:
            loop_command("true")
        assert exc.value.exit_code == 1
