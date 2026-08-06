"""Unit tests for wt task CLI commands and default invocation behavior."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.task.command import (
    task_list_command,
    task_run_command,
    task_show_command,
)
from getworktree.core.catalog.inventory import create_catalog_item, get_catalog_dir

runner = CliRunner()


def test_task_list_command_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    outcome = task_list_command(cwd=tmp_path)
    assert outcome.ok
    assert len(outcome.items) == 0


def test_task_list_command_with_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    # Create task blueprint files directly under .worktree/catalog/tasks/
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task1_path = tasks_dir / "run-lints.yml"
    task1_path.write_text(
        "name: run-lints\ndescription: Execute Ruff linter and formatter checks\nsummary: Runs ruff check and format\n",
        encoding="utf-8",
    )

    task2_path = tasks_dir / "run-tests.yml"
    task2_path.write_text(
        "name: run-tests\ndescription: Execute pytest test suite\nsummary: Runs pytest with coverage\n",
        encoding="utf-8",
    )

    outcome = task_list_command(cwd=tmp_path)
    assert outcome.ok
    assert len(outcome.items) == 2

    item_map = {i.name: i for i in outcome.items}
    assert "run-lints" in item_map
    assert (
        item_map["run-lints"].description == "Execute Ruff linter and formatter checks"
    )
    assert item_map["run-lints"].summary == "Runs ruff check and format"

    assert "run-tests" in item_map
    assert item_map["run-tests"].description == "Execute pytest test suite"
    assert item_map["run-tests"].summary == "Runs pytest with coverage"


def test_task_show_and_run_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    create_catalog_item("task", "sample-task", cwd=tmp_path)

    # Show valid task
    show_res = task_show_command("sample-task", cwd=tmp_path)
    assert show_res.ok
    assert show_res.item is not None
    assert show_res.item.name == "sample-task"
    assert show_res.content is not None

    # Show missing task
    show_missing = task_show_command("non-existent-task", cwd=tmp_path)
    assert not show_missing.ok
    assert "not found" in show_missing.errors[0]

    # Run valid task
    run_res = task_run_command("sample-task", cwd=tmp_path)
    assert run_res.ok
    assert run_res.run_record is not None
    assert run_res.run_record.task_name == "sample-task"

    # Run missing task
    run_missing = task_run_command("non-existent-task", cwd=tmp_path)
    assert not run_missing.ok
    assert "not found" in run_missing.errors[0]


def test_cli_wt_task_default_and_subcommands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task1_path = tasks_dir / "run-lints.yml"
    task1_path.write_text(
        "name: run-lints\ndescription: Execute Ruff linter and formatter checks\nsummary: Runs ruff check and format\n",
        encoding="utf-8",
    )

    # wt task (default invocation should match wt task list)
    res_default = runner.invoke(app, ["task"])
    assert res_default.exit_code == 0
    assert "Available Tasks:" in res_default.output
    assert "run-lints" in res_default.output

    # wt task list
    res_list = runner.invoke(app, ["task", "list"])
    assert res_list.exit_code == 0
    assert "Available Tasks:" in res_list.output
    assert "run-lints" in res_list.output
    assert res_default.output == res_list.output

    # wt task show run-lints
    res_show = runner.invoke(app, ["task", "show", "run-lints"])
    assert res_show.exit_code == 0
    assert "Task Blueprint:" in res_show.output

    # wt task run run-lints
    res_run = runner.invoke(app, ["task", "run", "run-lints"])
    assert res_run.exit_code == 0
    assert "Task Run Completed:" in res_run.output

    # wt task non-existent -> invalid subcommand error code 2
    res_invalid = runner.invoke(app, ["task", "non-existent"])
    assert res_invalid.exit_code == 2
    assert "No such command 'non-existent'" in res_invalid.output
