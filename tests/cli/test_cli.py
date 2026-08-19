"""CLI smoke tests for the Typer entrypoint."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli.cli import __version__, app

runner = CliRunner()


class CliSmokeTests:
    """Smoke tests for top-level CLI behavior."""

    def test_bare_invocation_prints_banner_and_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert "init" in result.stdout

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert __version__ in result.stdout

    def test_init_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (git_fs.base_path / ".worktree" / "config.json").is_file()
        assert (git_fs.base_path / ".worktree" / "data.db").is_file()

    def test_legacy_task_and_workflow_commands_unrecognized(self) -> None:
        result_task = runner.invoke(app, ["task"])
        assert result_task.exit_code == 2
        assert "No such command 'task'" in result_task.output

        result_workflow = runner.invoke(app, ["workflow"])
        assert result_workflow.exit_code == 2
        assert "No such command 'workflow'" in result_workflow.output
