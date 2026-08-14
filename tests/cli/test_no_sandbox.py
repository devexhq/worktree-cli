"""Unit tests for --no-sandbox CLI flag."""

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.task.command import task_list_command, task_run_command
from tests.helpers import FileSystem

runner = CliRunner()


def test_task_blueprint_use_sandbox_parsing(fs: FileSystem) -> None:
    fs.write_file(
        ".worktree/catalog/tasks/in-place-task.yml",
        {
            "name": "in-place-task",
            "description": "Run linters in-place",
            "summary": "In-place task",
            "use_sandbox": False,
            "commands": [{"name": "echo-test", "command": "echo test"}],
        },
    )

    outcome = task_list_command(cwd=fs.base_path)
    assert outcome.ok
    assert len(outcome.items) == 1
    assert outcome.items[0].name == "in-place-task"
    assert outcome.items[0].use_sandbox is False


def test_task_run_command_no_sandbox_flag(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.write_file(
        ".worktree/catalog/tasks/sample-task.yml",
        {
            "name": "sample-task",
            "description": "Sample task",
            "summary": "Sample task",
            "use_sandbox": True,
            "commands": [{"name": "test-step", "command": "echo hello"}],
        },
    )

    # Run with --no-sandbox
    res = task_run_command("sample-task", cwd=fs.base_path, no_sandbox=True)
    assert res.ok

    # CLI test
    result = runner.invoke(app, ["task", "run", "sample-task", "--no-sandbox"])
    assert result.exit_code == 0
    assert "Sandbox: In-place (workspace)" in result.output


def test_task_run_honors_blueprint_use_sandbox_false(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blueprint use_sandbox: false runs in-place without needing --no-sandbox."""
    monkeypatch.chdir(fs.base_path)
    fs.write_file(
        ".worktree/catalog/tasks/in-place-task.yml",
        {
            "name": "in-place-task",
            "description": "Writes a side-effect file in-place",
            "summary": "In-place side effect",
            "use_sandbox": False,
            "steps": [
                {"run": 'echo "from-task" >> output.log'},
            ],
        },
    )

    res = task_run_command("in-place-task", cwd=fs.base_path, no_sandbox=False)
    assert res.ok
    assert (fs.base_path / "output.log").read_text(encoding="utf-8") == "from-task\n"

    result = runner.invoke(app, ["task", "run", "in-place-task"])
    assert result.exit_code == 0
    assert "Sandbox: In-place (workspace)" in result.output
    assert "Sandbox: Active" not in result.output
