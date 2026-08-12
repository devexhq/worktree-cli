"""Tests for `wt workflow show`."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.workflow.command import workflow_show_command
from getworktree.core.db import WorkflowsDb
from tests.helpers import GitFileSystem

runner = CliRunner()


class WorkflowShowCommandDirectTests:
    """Direct workflow_show_command tests."""

    def test_workflow_show_success(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        WorkflowsDb(git_fs.base_path).insert(
            session_id="wf-12345",
            workflow_name="fix-tests",
            branch_name="wt/fix-tests",
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_show_command("wf-12345", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Workflow Session: wf-12345" in out
        assert "Name:             fix-tests" in out
        assert "Branch:           wt/fix-tests" in out

    def test_workflow_show_not_found(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        with pytest.raises(typer.Exit) as exc_info:
            workflow_show_command("nonexistent", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Show Failed" in out
        assert "Workflow session 'nonexistent' not found." in out

    def test_workflow_show_uninitialized(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_show_command("wf-12345", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Show Failed" in out


class WorkflowShowCliTests:
    """CliRunner coverage for workflow show."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "show", "--help"])
        assert result.exit_code == 0
        assert "Show details for a specific workflow session" in result.stdout

    def test_cli_show_success(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        WorkflowsDb(git_fs.base_path).insert(
            session_id="wf-55555",
            workflow_name="test-workflow",
            branch_name="wt/test-workflow",
        )

        result = runner.invoke(app, ["workflow", "show", "wf-55555"])
        assert result.exit_code == 0
        assert "Workflow Session: wf-55555" in result.stdout
