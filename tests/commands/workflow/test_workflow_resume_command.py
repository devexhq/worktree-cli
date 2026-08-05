"""Tests for `wt workflow resume`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.workflow.command import workflow_resume_command
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import insert_sandbox

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


class WorkflowResumeCommandDirectTests:
    """Direct workflow_resume_command tests."""

    def test_workflow_resume_success(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)

        insert_sandbox(
            id="wf-99999",
            branch_name="wt/resume-me",
            base_commit="HEAD",
            sandbox_path=git_repo / ".worktree" / "sandboxes" / "wf-99999",
            name="resume-me",
            cwd=git_repo,
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-99999", cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Resuming workflow session 'wf-99999'..." in out

    def test_workflow_resume_not_found(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("nonexistent", cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out
        assert "Workflow session 'nonexistent' not found." in out

    def test_workflow_resume_uninitialized(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-99999", cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out


class WorkflowResumeCliTests:
    """CliRunner coverage for workflow resume."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "resume", "--help"])
        assert result.exit_code == 0
        assert "Resume an interrupted workflow session" in result.stdout

    def test_cli_resume_success(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_repo(git_repo)
        insert_sandbox(
            id="wf-88888",
            branch_name="wt/resume-cli",
            base_commit="HEAD",
            sandbox_path=git_repo / ".worktree" / "sandboxes" / "wf-88888",
            name="resume-cli",
            cwd=git_repo,
        )

        result = runner.invoke(app, ["workflow", "resume", "wf-88888"])
        assert result.exit_code == 0
        assert "Resuming workflow session 'wf-88888'..." in result.stdout
