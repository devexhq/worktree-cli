"""Comprehensive CLI unit tests for task execution (wt task run)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.task.command import task_run_command
from getworktree.core.catalog.inventory import get_catalog_dir
from getworktree.core.db import get_task_run

runner = CliRunner()


def test_task_run_command_steps_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_file = tasks_dir / "build-task.yml"
    task_file.write_text(
        "name: build-task\n"
        "description: Build and test task\n"
        "summary: Build and test\n"
        "use_git_worktree: false\n"
        "commands:\n"
        "  - name: step-1\n"
        "    command: echo step1\n"
        "  - name: step-2\n"
        "    command: echo step2\n",
        encoding="utf-8",
    )

    res = task_run_command("build-task", cwd=tmp_path, session_id="task_build_1")
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "completed"

    rec = get_task_run("task_build_1", cwd=tmp_path)
    assert rec is not None
    assert rec.status.value == "completed"


def test_task_run_cli_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_file = tasks_dir / "lint-task.yml"
    task_file.write_text(
        "name: lint-task\n"
        "description: Lint task\n"
        "summary: Lint task\n"
        "use_git_worktree: false\n"
        "commands:\n"
        "  - name: check-lints\n"
        "    command: echo lint ok\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["task", "run", "lint-task", "--no-sandbox", "--agent", "claude-3-5-sonnet"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output
    assert "Sandbox: In-place (workspace)" in result.output


def test_task_run_step_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_file = tasks_dir / "failing-task.yml"
    task_file.write_text(
        "name: failing-task\n"
        "description: Failing task\n"
        "summary: Failing task\n"
        "use_git_worktree: false\n"
        "commands:\n"
        "  - name: pass-step\n"
        "    command: echo ok\n"
        "  - name: fail-step\n"
        "    command: exit 1\n"
        "    failure_action: abort\n"
        "  - name: unreachable-step\n"
        "    command: echo should not run\n",
        encoding="utf-8",
    )

    res = task_run_command("failing-task", cwd=tmp_path, session_id="task_fail_1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "failed"

    rec = get_task_run("task_fail_1", cwd=tmp_path)
    assert rec is not None
    assert rec.status.value == "failed"
    assert "fail-step" in rec.error_message
