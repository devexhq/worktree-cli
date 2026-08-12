"""Comprehensive CLI unit tests for task execution (wt task run)."""

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.task.command import task_run_command
from getworktree.core.db import TasksDb
from tests.helpers import FileSystem

runner = CliRunner()


def test_task_run_command_steps_execution(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.write_file(
        ".worktree/catalog/tasks/build-task.yml",
        {
            "name": "build-task",
            "description": "Build and test task",
            "summary": "Build and test",
            "use_git_worktree": False,
            "commands": [
                {"name": "step-1", "command": "echo step1"},
                {"name": "step-2", "command": "echo step2"},
            ],
        },
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
    fs.write_file(
        ".worktree/catalog/tasks/lint-task.yml",
        {
            "name": "lint-task",
            "description": "Lint task",
            "summary": "Lint task",
            "use_git_worktree": False,
            "commands": [{"name": "check-lints", "command": "echo lint ok"}],
        },
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
    fs.write_file(
        ".worktree/catalog/tasks/failing-task.yml",
        {
            "name": "failing-task",
            "description": "Failing task",
            "summary": "Failing task",
            "use_git_worktree": False,
            "commands": [
                {"name": "pass-step", "command": "echo ok"},
                {"name": "fail-step", "command": "exit 1", "on_failure": "abort"},
                {"name": "unreachable-step", "command": "echo should not run"},
            ],
        },
    )

    res = task_run_command("failing-task", cwd=fs.base_path, session_id="task_fail_1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "failed"

    rec = TasksDb(fs.base_path).get("task_fail_1")
    assert rec is not None
    assert rec.status.value == "failed"
    assert "fail-step" in rec.error_message
