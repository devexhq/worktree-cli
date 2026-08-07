"""Tests for `wt workflow` and `wt workflow list`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.workflow.command import workflow_list_command
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import insert_workflow_run

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


def _init_repo(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    return config_path


class WorkflowListCommandDirectTests:
    """Direct workflow_list_command tests."""

    def test_success_recorded_workflows(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)

        insert_workflow_run(
            session_id="wf-20260805-01",
            workflow_name="refactor-pipeline",
            branch_name="wt/refactor-pipe",
            cwd=git_repo,
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Recorded Workflows" in out
        assert "wf-20260805-01" in out
        assert "refactor-pipeline" in out
        assert "wt/refactor-pipe" in out

    def test_empty_recorded_workflows(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "No recorded workflows found." in out

    def test_uninitialized_repo_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow List Failed" in out


class WorkflowListCliTests:
    """CliRunner coverage for registration, default invocation, and unknown subcommand."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "list", "--help"])
        assert result.exit_code == 0
        assert "List workflow run sessions" in result.stdout

    def test_cli_success(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)
        insert_workflow_run(
            session_id="wf-20260805-01",
            workflow_name="refactor-pipeline",
            branch_name="wt/refactor-pipe",
            cwd=git_repo,
        )

        result = runner.invoke(app, ["workflow", "list"])
        assert result.exit_code == 0
        assert "Recorded Workflows" in result.stdout
        assert "wf-20260805-01" in result.stdout

    def test_cli_default_invocation_matches_list(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)
        insert_workflow_run(
            session_id="wf-20260805-02",
            workflow_name="run-tests",
            branch_name="wt/run-tests",
            cwd=git_repo,
        )

        res_default = runner.invoke(app, ["workflow"])
        res_list = runner.invoke(app, ["workflow", "list"])

        assert res_default.exit_code == 0
        assert res_list.exit_code == 0
        assert res_default.stdout == res_list.stdout

    def test_cli_unknown_subcommand_exits_code_2(self) -> None:
        result = runner.invoke(app, ["workflow", "unknown"])
        assert result.exit_code == 2

    def test_cli_uninitialized(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["workflow", "list"])
        assert result.exit_code == 1
        assert "Workflow List Failed" in result.stdout
