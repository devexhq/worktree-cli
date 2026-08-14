"""Comprehensive CLI unit tests for task execution (wt task run)."""

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.task.command import task_run_command
from getworktree.core.db import RunStatus, TasksDb
from getworktree.core.runtime import RunOutcome
from tests.helpers import FileSystem

runner = CliRunner()


def test_task_run_command_steps_execution(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "build-task",
        description="Build and test task",
        summary="Build and test",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2"},
        ],
    )

    res = task_run_command("build-task", cwd=fs.base_path, session_id="task_build_1")
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "completed"

    rec = TasksDb(fs.base_path).get("task_build_1")
    assert rec is not None
    assert rec.status.value == "completed"


def test_task_run_cli_options(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "lint-task",
        description="Lint task",
        summary="Lint task",
        use_sandbox=False,
        steps=[{"id": "check-lints", "run": "echo lint ok"}],
    )

    result = runner.invoke(
        app,
        ["task", "run", "lint-task", "--no-sandbox", "--agent", "claude-3-5-sonnet"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output
    assert "Sandbox: In-place (workspace)" in result.output


def test_task_run_step_failure_aborts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "failing-task",
        description="Failing task",
        summary="Failing task",
        use_sandbox=False,
        steps=[
            {"id": "pass-step", "run": "echo ok"},
            {"id": "fail-step", "run": "exit 1", "on_failure": "abort"},
            {"id": "unreachable-step", "run": "echo should not run"},
        ],
    )

    res = task_run_command("failing-task", cwd=fs.base_path, session_id="task_fail_1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "failed"

    rec = TasksDb(fs.base_path).get("task_fail_1")
    assert rec is not None
    assert rec.status.value == "failed"
    assert rec.error_message is not None
    assert "fail-step" in rec.error_message


def test_task_run_keep_retains_sandbox(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "keep-task",
        use_sandbox=True,
        steps=[{"id": "ok", "run": "echo ok"}],
    )

    kept_path = fs.base_path / ".worktree" / "sandboxes" / "kept"
    kept_path.mkdir(parents=True, exist_ok=True)

    def _fake_run_task(definition, cwd, *, use_sandbox=True, keep=False, agent=None, observer=None):
        if observer is not None:
            observer.on_sandbox_ready(kept_path, True)
            observer.on_sandbox_cleanup(True, kept_path)
        return RunOutcome(
            status=RunStatus.COMPLETED,
            step_results=[],
            error_message=None,
            sandbox_kept=True,
            sandbox_path=kept_path,
        )

    monkeypatch.setattr("getworktree.cli.task.command.run_task", _fake_run_task)

    result = runner.invoke(app, ["task", "run", "keep-task", "--keep"])
    assert result.exit_code == 0
    assert "Sandbox: Retained" in result.output


def test_task_run_missing_task_skips_db_insert(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    insert = MagicMock()
    monkeypatch.setattr(TasksDb, "insert", insert)

    res = task_run_command("missing-task", cwd=fs.base_path, session_id="task_missing")
    assert not res.ok
    assert res.run_record is None
    insert.assert_not_called()
    assert TasksDb(fs.base_path).get("task_missing") is None


def test_task_run_cancelled_status(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "cancel-task",
        use_sandbox=False,
        steps=[{"id": "ok", "run": "echo ok"}],
    )

    def _fake_run_task(definition, cwd, *, use_sandbox=True, keep=False, agent=None, observer=None):
        return RunOutcome(
            status=RunStatus.CANCELLED,
            step_results=[],
            error_message="Execution cancelled by user.",
            sandbox_kept=False,
            sandbox_path=cwd,
        )

    monkeypatch.setattr("getworktree.cli.task.command.run_task", _fake_run_task)

    res = task_run_command("cancel-task", cwd=fs.base_path, session_id="task_canc1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "cancelled"

    rec = TasksDb(fs.base_path).get("task_canc1")
    assert rec is not None
    assert rec.status.value == "cancelled"
    assert "cancelled" in (rec.error_message or "").lower()
