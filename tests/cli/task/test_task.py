"""Unit tests for wt task CLI commands and default invocation behavior."""

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem
from worktree.cli import app
from worktree.cli.task.command import (
    task_list_command,
    task_run_command,
    task_show_command,
)
from worktree.core.catalog.services.inventory import create_catalog_item
from worktree.core.db import TasksDb

runner = CliRunner()


def test_task_list_command_empty(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    # Blueprints alone must not appear in task list output.
    fs.create_task_file("run-lints", use_sandbox=False)

    outcome = task_list_command(cwd=fs.base_path)
    assert outcome.ok
    assert outcome.runs == []

    res_cli = runner.invoke(app, ["task", "list"])
    assert res_cli.exit_code == 0
    assert "No recorded task runs found." in res_cli.output
    assert "Available Tasks:" not in res_cli.output
    assert "run-lints" not in res_cli.output


def test_task_show_and_run_commands(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)

    create_catalog_item("task", "sample-task", cwd=fs.base_path)
    fs.write_file(
        ".worktree/catalog/tasks/sample-task.yml",
        "name: sample-task\ndescription: Custom task blueprint\nuse_sandbox: false\nsteps: []\n",
    )

    # Show valid task
    show_res = task_show_command("sample-task", cwd=fs.base_path)
    assert show_res.ok
    assert show_res.item is not None
    assert show_res.item.name == "sample-task"
    assert show_res.content is not None

    # Show missing task
    show_missing = task_show_command("non-existent-task", cwd=fs.base_path)
    assert not show_missing.ok
    assert "not found" in show_missing.errors[0].lower()

    # Run valid task
    run_res = task_run_command("sample-task", cwd=fs.base_path)
    assert run_res.ok
    assert run_res.run_record is not None
    assert run_res.run_record.task_name == "sample-task"

    # Run missing task
    run_missing = task_run_command("non-existent-task", cwd=fs.base_path)
    assert not run_missing.ok
    assert "not found" in run_missing.errors[0].lower()


def test_cli_wt_task_default_and_subcommands(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)

    fs.create_task_file(
        "run-lints",
        description="Execute Ruff linter and formatter checks",
        summary="Runs ruff check and format",
        use_sandbox=False,
    )

    # wt task (default invocation should match wt task list) — runs only
    res_default = runner.invoke(app, ["task"])
    assert res_default.exit_code == 0
    assert "No recorded task runs found." in res_default.output
    assert "Available Tasks:" not in res_default.output

    # wt task list
    res_list = runner.invoke(app, ["task", "list"])
    assert res_list.exit_code == 0
    assert res_default.output == res_list.output

    # wt task show run-lints
    res_show = runner.invoke(app, ["task", "show", "run-lints"])
    assert res_show.exit_code == 0
    assert "Task Blueprint:" in res_show.output

    # wt task run run-lints
    res_run = runner.invoke(app, ["task", "run", "run-lints"])
    assert res_run.exit_code == 0
    assert "Task Run Completed:" in res_run.output

    # After a run, list shows the recorded session (not blueprints)
    res_list_after = runner.invoke(app, ["task", "list"])
    assert res_list_after.exit_code == 0
    assert "Recorded Task Runs:" in res_list_after.output
    assert "run-lints" in res_list_after.output
    assert "Available Tasks:" not in res_list_after.output

    # wt task non-existent -> invalid subcommand error code 2
    res_invalid = runner.invoke(app, ["task", "non-existent"])
    assert res_invalid.exit_code == 2
    assert "No such command 'non-existent'" in res_invalid.output


def test_task_run_status_transitions_and_persistence(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)

    fs.create_task_file(
        "passing-task",
        use_sandbox=False,
        steps=[{"id": "ok", "run": "echo ok"}],
    )
    fs.create_task_file(
        "failing-task",
        use_sandbox=False,
        steps=[{"id": "boom", "run": "exit 1"}],
    )

    # 1. Success task run
    res_success = task_run_command("passing-task", cwd=fs.base_path, session_id="task_succ1")
    assert res_success.ok
    assert res_success.run_record is not None
    assert res_success.run_record.status.value == "completed"

    rec_succ = TasksDb(fs.base_path).get("task_succ1")
    assert rec_succ is not None
    assert rec_succ.status.value == "completed"
    assert rec_succ.completed_at is not None
    assert rec_succ.error_message is None

    # 2. Failed task run via real failing step
    res_failed = task_run_command("failing-task", cwd=fs.base_path, session_id="task_fail1")
    assert not res_failed.ok
    assert res_failed.run_record is not None
    assert res_failed.run_record.status.value == "failed"
    assert res_failed.errors

    rec_fail = TasksDb(fs.base_path).get("task_fail1")
    assert rec_fail is not None
    assert rec_fail.status.value == "failed"
    assert rec_fail.completed_at is not None
    assert rec_fail.error_message is not None
    assert "boom" in rec_fail.error_message

    # 3. Cancelled task run (runtime returns CANCELLED)
    from worktree.core.db import RunStatus
    from worktree.core.runtime import RunOutcome

    def _cancel_run(
        definition,
        cwd,
        *,
        use_sandbox=True,
        keep=False,
        agent=None,
        observer=None,
        inputs=None,
        **kwargs,
    ):
        return RunOutcome(
            status=RunStatus.CANCELLED,
            step_results=[],
            error_message="Execution cancelled by user.",
            sandbox_kept=False,
            sandbox_path=cwd,
        )

    monkeypatch.setattr("worktree.cli.task.command.run_task", _cancel_run)
    res_cancel = task_run_command(
        "passing-task",
        cwd=fs.base_path,
        session_id="task_canc1",
    )
    assert not res_cancel.ok
    assert res_cancel.run_record is not None
    assert res_cancel.run_record.status.value == "cancelled"

    rec_canc = TasksDb(fs.base_path).get("task_canc1")
    assert rec_canc is not None
    assert rec_canc.status.value == "cancelled"
    assert rec_canc.completed_at is not None
    assert "cancelled" in (rec_canc.error_message or "").lower()


def test_task_run_db_fault_tolerance(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "sample-task",
        use_sandbox=False,
        steps=[],
    )

    # Monkeypatch TasksDb.insert to raise DB exception
    def _faulty_insert(*args, **kwargs):
        raise RuntimeError("Database locked")

    monkeypatch.setattr(TasksDb, "insert", _faulty_insert)

    res = task_run_command("sample-task", cwd=fs.base_path)
    assert res.ok
    assert any("Failed to record task run start" in w for w in res.warnings)


def test_task_list_displays_recorded_runs(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "sample-task",
        use_sandbox=False,
        steps=[],
    )

    # Execute a task to record it in DB
    task_run_command("sample-task", cwd=fs.base_path, session_id="task_rec1")

    # Call task_list_command and verify runs are present in outcome and rendering
    outcome = task_list_command(cwd=fs.base_path)
    assert outcome.ok
    assert len(outcome.runs) == 1
    assert outcome.runs[0].session_id == "task_rec1"

    # CLI check for list table rendering
    res_cli = runner.invoke(app, ["task", "list"])
    assert res_cli.exit_code == 0
    assert "Recorded Task Runs:" in res_cli.output
    assert "task_rec1" in res_cli.output
