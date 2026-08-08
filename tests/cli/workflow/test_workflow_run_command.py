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
from getworktree.core.config.generator import generate_default_config
from getworktree.core.workflows.seeder import seed_starter_workflows

runner = CliRunner()


def _init_with_workflows(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    workflows_dir = repo / ".worktree" / "workflows"
    assert seed_starter_workflows(workflows_dir).ok
    return workflows_dir


class WorkflowRunCommandDirectTests:
    """Direct tests for workflow_run_command."""

    def test_uninitialized_worktree_exits_1(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 1

    def test_nonexistent_workflow_exits_1(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_workflows(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("no-such-workflow", cwd=git_repo)
        assert exc_info.value.exit_code == 1

    def test_valid_workflow_reports_not_implemented(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_workflows(git_repo)
        with pytest.raises(typer.Exit) as exc_info:
            workflow_run_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 1


class WorkflowRunCliTests:
    """CliRunner coverage for wt workflow run."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "run", "--help"])
        assert result.exit_code == 0
        assert "Run a workflow" in result.stdout

    def test_valid_workflow_reports_not_implemented(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_workflows(git_repo)
        result = runner.invoke(app, ["workflow", "run", "fix-tests"])
        assert result.exit_code == 1
        assert "Workflow Run Not Implemented" in result.stdout

    def test_nonexistent_workflow_exits_1(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_workflows(git_repo)
        result = runner.invoke(app, ["workflow", "run", "no-such-workflow"])
        assert result.exit_code == 1
