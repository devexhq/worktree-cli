"""Unit tests for --no-sandbox CLI flag."""

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem
from worktree.cli import app
from worktree.cli.context import get_cli_context
from worktree.core.blueprint import BlueprintRunService
from worktree.core.task import resolve_and_load_task

runner = CliRunner()


class NoSandboxCliTests:
    """Tests for in-place blueprint execution and --no-sandbox CLI flag."""

    def test_task_blueprint_use_sandbox_parsing(self, fs: FileSystem) -> None:
        fs.write_file(
            ".worktree/catalog/tasks/in-place-task.yml",
            {
                "name": "in-place-task",
                "description": "Run linters in-place",
                "summary": "In-place task",
                "use_sandbox": False,
                "steps": [{"id": "echo-test", "run": "echo test"}],
            },
        )

        result = resolve_and_load_task("in-place-task", path=fs.base_path)
        assert result.ok
        assert result.definition is not None
        assert result.definition.use_sandbox is False

    def test_run_command_no_sandbox_flag(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(fs.base_path)
        fs.write_file(
            ".worktree/catalog/tasks/sample-task.yml",
            {
                "name": "sample-task",
                "description": "Sample task",
                "summary": "Sample task",
                "use_sandbox": False,
                "steps": [{"id": "test-step", "run": "echo hello"}],
            },
        )

        # Run with BlueprintRunService --no-sandbox
        ctx = get_cli_context(cwd=fs.base_path)
        res = BlueprintRunService(
            name="sample-task",
            path=ctx.cwd,
            runs_db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
            no_sandbox=True,
        ).execute()
        assert res.ok

        # CLI test
        result = runner.invoke(app, ["run", "sample-task", "--no-sandbox"])
        assert result.exit_code == 0
        assert "Sandbox: In-place (workspace)" in result.output
