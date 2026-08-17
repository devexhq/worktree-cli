"""Tests for `wt workflow resume`."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.workflow.command import workflow_resume_command
from worktree.core.db import SandboxesDb

runner = CliRunner()


class WorkflowResumeCommandDirectTests:
    """Direct workflow_resume_command tests."""

    def test_workflow_resume_success(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        SandboxesDb(git_fs.base_path).insert(
            id="wf-99999",
            branch_name="wt/resume-me",
            base_commit="HEAD",
            sandbox_path=git_fs.base_path / ".worktree" / "sandboxes" / "wf-99999",
            name="resume-me",
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-99999", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Resuming workflow session 'wf-99999'..." in out

    def test_workflow_resume_not_found(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("nonexistent", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out
        assert "Workflow session 'nonexistent' not found." in out

    def test_workflow_resume_uninitialized(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-99999", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out


class WorkflowResumeCliTests:
    """CliRunner coverage for workflow resume."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "resume", "--help"])
        assert result.exit_code == 0
        assert "Resume an interrupted workflow session" in result.stdout

    def test_cli_resume_success(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        SandboxesDb(git_fs.base_path).insert(
            id="wf-88888",
            branch_name="wt/resume-cli",
            base_commit="HEAD",
            sandbox_path=git_fs.base_path / ".worktree" / "sandboxes" / "wf-88888",
            name="resume-cli",
        )

        result = runner.invoke(app, ["workflow", "resume", "wf-88888"])
        assert result.exit_code == 0
        assert "Resuming workflow session 'wf-88888'..." in result.stdout
