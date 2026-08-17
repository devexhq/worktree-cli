"""Tests for `wt workflow resume`."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.workflow.command import workflow_resume_command
from worktree.core.db import RunStatus, WorkflowsDb
from worktree.core.runtime import RunCheckpoint
from worktree.core.step import StepResult

runner = CliRunner()


def _failed_result(step_id: str = "step-1") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="nope",
        duration_seconds=0.01,
        error_message="boom",
    )


def _checkpoint(**overrides: object) -> RunCheckpoint:
    payload: dict[str, object] = {
        "next_step_index": 0,
        "step_results": [],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": False,
        "pending_step_id": "step-1",
        "diagnostic": "Step 'step-1' failed: boom",
        "pending_result": _failed_result(),
    }
    payload.update(overrides)
    return RunCheckpoint.model_validate(payload)


def _insert_workflow(
    git_fs: GitFileSystem,
    session_id: str,
    *,
    status: RunStatus = RunStatus.PAUSED,
    checkpoint: RunCheckpoint | None = None,
    workflow_name: str = "resume-demo",
) -> None:
    db = WorkflowsDb(git_fs.base_path)
    db.insert(
        session_id=session_id,
        workflow_name=workflow_name,
        branch_name="wt/resume",
        status=RunStatus.RUNNING,
    )
    if status is RunStatus.PAUSED:
        raw = checkpoint.model_dump_json() if checkpoint is not None else None
        db.save_pause(session_id, raw or "", "paused")
        return
    db.update_status(session_id, status)


class WorkflowResumeCommandDirectTests:
    """Direct workflow_resume_command tests."""

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

    def test_workflow_resume_wrong_status(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        _insert_workflow(git_fs, "wf-running", status=RunStatus.RUNNING)

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-running", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Cannot resume session 'wf-running': status is 'running' (expected paused)." in out

    def test_workflow_resume_missing_sandbox(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        missing = git_fs.base_path / ".worktree" / "sandboxes" / "gone"
        _insert_workflow(
            git_fs,
            "wf-sandbox",
            checkpoint=_checkpoint(use_sandbox=True, sandbox_path=str(missing)),
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-sandbox", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Cannot resume session 'wf-sandbox'" in out
        assert "sandbox path" in out
        assert str(missing) in out

    def test_workflow_resume_corrupt_checkpoint(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        db = WorkflowsDb(git_fs.base_path)
        db.insert(session_id="wf-bad", workflow_name="resume-demo", branch_name="wt/resume")
        db.save_pause("wf-bad", "{not-json", "paused")

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-bad", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Cannot resume session 'wf-bad': checkpoint is missing or corrupt." in out

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

    def test_cli_resume_not_found(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        result = runner.invoke(app, ["workflow", "resume", "wf-missing"])
        assert result.exit_code == 1
        assert "Workflow session 'wf-missing' not found." in result.stdout
