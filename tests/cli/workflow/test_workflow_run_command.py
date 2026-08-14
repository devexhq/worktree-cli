"""Tests for ``wt workflow run`` UX and exit codes.

Workflow execution is not implemented yet (tracked in
getworktree/getworktree#171, #172, #173); ``wt workflow run`` validates the
requested workflow definition and reports that step execution is pending.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.workflow.command import workflow_run_command
from getworktree.core.catalog.services.inventory import scan_and_index_catalog
from tests.helpers import GitFileSystem

runner = CliRunner()


def _init_with_workflows(git_fs: GitFileSystem) -> Path:
    git_fs.init_repo()
    workflows_dir = git_fs.base_path / ".worktree" / "catalog" / "workflows"
    git_fs.create_workflow_file(
        "fix-tests",
        id="fix-tests",
        steps=[{"id": "step-1", "run": "echo hi"}],
    )
    scan_and_index_catalog(cwd=git_fs.base_path)
    return workflows_dir


class WorkflowRunCommandDirectTests:
    """Direct tests for workflow_run_command."""

    def test_uninitialized_worktree_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

    def test_nonexistent_workflow_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("no-such-workflow", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

    def test_valid_workflow_reports_not_implemented(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1


class WorkflowRunCliTests:
    """CliRunner coverage for wt workflow run."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "run", "--help"])
        assert result.exit_code == 0
        assert "Run a workflow" in result.stdout

    def test_valid_workflow_reports_not_implemented(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        result = runner.invoke(app, ["workflow", "run", "fix-tests"])
        assert result.exit_code == 1
        assert "Workflow Run Not Implemented" in result.stdout

    def test_nonexistent_workflow_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        result = runner.invoke(app, ["workflow", "run", "no-such-workflow"])
        assert result.exit_code == 1
