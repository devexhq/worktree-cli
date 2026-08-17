"""Tests for ``wt workflow run`` UX and exit codes.

Workflow execution is not implemented yet (tracked in
devexhq/worktree-cli#171, #172, #173); ``wt workflow run`` validates the
requested workflow definition and reports that step execution is pending.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.workflow.command import workflow_run_command
from worktree.core.catalog.services.inventory import scan_and_index_catalog

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


class WorkflowRunInputTests:
    """Input validation gate for wt workflow run."""

    def test_missing_required_input_fails_before_not_implemented(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "commit-flow",
            id="commit-flow",
            inputs={
                "message": {
                    "type": "string",
                    "required": True,
                    "aliases": ["-m", "--message"],
                }
            },
            steps=[{"id": "step-1", "run": "echo hi"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "commit-flow"])
        assert result.exit_code == 1
        assert "Missing required input 'message'" in result.stdout
        assert "Workflow Run Not Implemented" not in result.stdout

    def test_provided_input_reaches_not_implemented(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "commit-flow",
            id="commit-flow",
            inputs={
                "message": {
                    "type": "string",
                    "required": True,
                    "aliases": ["-m", "--message"],
                }
            },
            steps=[{"id": "step-1", "run": "echo hi"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "commit-flow", "-m", "hi"])
        assert result.exit_code == 1
        assert "Workflow Run Not Implemented" in result.stdout
