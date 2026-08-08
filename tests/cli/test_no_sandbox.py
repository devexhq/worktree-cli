"""Unit tests for --no-sandbox CLI flag."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.task.command import task_list_command, task_run_command
from getworktree.core.catalog.inventory import get_catalog_dir

runner = CliRunner()


def test_task_blueprint_use_git_worktree_parsing(tmp_path: Path) -> None:
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_file = tasks_dir / "in-place-task.yml"
    task_file.write_text(
        "name: in-place-task\n"
        "description: Run linters in-place\n"
        "summary: In-place task\n"
        "use_git_worktree: false\n"
        "commands:\n"
        "  - name: echo-test\n"
        "    command: echo test\n",
        encoding="utf-8",
    )

    outcome = task_list_command(cwd=tmp_path)
    assert outcome.ok
    assert len(outcome.items) == 1
    assert outcome.items[0].name == "in-place-task"
    assert outcome.items[0].use_git_worktree is False


def test_task_run_command_no_sandbox_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    tasks_dir = get_catalog_dir(tmp_path) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_file = tasks_dir / "sample-task.yml"
    task_file.write_text(
        "name: sample-task\n"
        "description: Sample task\n"
        "summary: Sample task\n"
        "use_git_worktree: false\n"
        "commands:\n"
        "  - name: test-step\n"
        "    command: echo hello\n",
        encoding="utf-8",
    )

    # Run with --no-sandbox
    res = task_run_command("sample-task", cwd=tmp_path, no_sandbox=True)
    assert res.ok

    # CLI test
    result = runner.invoke(app, ["task", "run", "sample-task", "--no-sandbox"])
    assert result.exit_code == 0
    assert "Sandbox: In-place (workspace)" in result.output
