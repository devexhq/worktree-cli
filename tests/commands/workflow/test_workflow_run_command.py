"""Tests for ``wt workflow run`` UX and exit codes."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.workflow.command import workflow_run_command
from getworktree.commands.workflow.renderers import (
    exit_code_for_status,
)
from getworktree.core.config.generator import generate_default_config
from getworktree.core.loops.runner import (
    AttemptRecord,
    LoopFinalStatus,
    LoopRunResult,
    StopReason,
)
from getworktree.core.loops.seeder import seed_starter_loops

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
    subprocess.run(
        ["git", "config", "user.name", "Test Runner"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


def _init_with_loops(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    loops_dir = repo / ".worktree" / "loops"
    assert seed_starter_loops(loops_dir).ok
    return loops_dir


def _make_result(
    status: LoopFinalStatus,
    *,
    stop_reason: StopReason = StopReason.TRIGGER_PASSED,
    session_id: str = "sbx_a1b2c3d4",
    loop_name: str = "fix-tests",
    attempts: list[AttemptRecord] | None = None,
    retained: bool = False,
    sandbox_path: Path | None = None,
) -> LoopRunResult:
    att_list = (
        attempts
        if attempts is not None
        else [
            AttemptRecord(
                attempt=1,
                started_at="2026-08-05T00:00:00Z",
                trigger_status="passed",
                trigger_duration_ms=120,
            )
        ]
    )
    return LoopRunResult(
        status=status,
        session_id=session_id,
        loop_name=loop_name,
        sandbox_path=sandbox_path if retained else None,
        attempts=att_list,
        stop_reason=stop_reason,
        errors=[],
        warnings=[],
        max_attempts=1,
        sandbox_retained=retained,
    )


class ExitCodeMappingTests:
    """Tests for exit_code_for_status mapping."""

    def test_passed_exits_0(self) -> None:
        assert exit_code_for_status(LoopFinalStatus.PASSED) == 0

    def test_failed_exits_1(self) -> None:
        assert exit_code_for_status(LoopFinalStatus.FAILED) == 1

    def test_unfixable_exits_2(self) -> None:
        assert exit_code_for_status(LoopFinalStatus.UNFIXABLE) == 2

    def test_aborted_exits_130(self) -> None:
        assert exit_code_for_status(LoopFinalStatus.ABORTED) == 130


class WorkflowRunCommandDirectTests:
    """Direct tests for workflow_run_command."""

    def test_invalid_max_attempts_exits_1(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", max_attempts=0, cwd=git_repo)
        assert exc_info.value.exit_code == 1

    def test_uninitialized_worktree_exits_1(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 1

    def test_nonexistent_workflow_exits_1(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("no-such-workflow", cwd=git_repo)
        assert exc_info.value.exit_code == 1

    def test_successful_run_exits_0(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        def mock_runner(*args: Any, **kwargs: Any) -> LoopRunResult:
            return _make_result(LoopFinalStatus.PASSED)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo, run_loop_fn=mock_runner)
        assert exc_info.value.exit_code == 0

    def test_failed_run_exits_1(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        def mock_runner(*args: Any, **kwargs: Any) -> LoopRunResult:
            return _make_result(
                LoopFinalStatus.FAILED,
                stop_reason=StopReason.MAX_ATTEMPTS_EXHAUSTED,
            )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo, run_loop_fn=mock_runner)
        assert exc_info.value.exit_code == 1

    def test_unfixable_run_exits_2(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        def mock_runner(*args: Any, **kwargs: Any) -> LoopRunResult:
            return _make_result(
                LoopFinalStatus.UNFIXABLE,
                stop_reason=StopReason.AGENT_UNFIXABLE,
            )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo, run_loop_fn=mock_runner)
        assert exc_info.value.exit_code == 2


class WorkflowRunCliTests:
    """CliRunner coverage for wt workflow run."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "run", "--help"])
        assert result.exit_code == 0
        assert "Run a workflow in an isolated git worktree sandbox" in result.stdout
