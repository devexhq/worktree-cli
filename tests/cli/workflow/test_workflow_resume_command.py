from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.workflow.command import workflow_resume_command
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import BlueprintKind, RunsDb, RunStatus
from worktree.core.runtime import FailurePromptDecision, RunCheckpoint, RunOutcome
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
    db = RunsDb(git_fs.base_path)
    db.create(
        session_id=session_id,
        blueprint_name=workflow_name,
        kind=BlueprintKind.WORKFLOW,
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

    def test_task_session_id_refused_direct(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        runs_db = RunsDb(git_fs.base_path)
        runs_db.create(
            session_id="task-session-1", blueprint_name="sample-task", kind=BlueprintKind.TASK, status=RunStatus.RUNNING
        )
        runs_db.save_pause("task-session-1", _checkpoint().model_dump_json(), "paused")

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("task-session-1", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out
        assert "Workflow session 'task-session-1' not found." in out

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
        db = RunsDb(git_fs.base_path)
        db.create(
            session_id="wf-bad", blueprint_name="resume-demo", kind=BlueprintKind.WORKFLOW, branch_name="wt/resume"
        )
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

    def test_workflow_resume_success(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "resume-demo",
            id="resume-demo",
            steps=[{"id": "step-1", "run": "echo resume-ok", "on_failure": "prompt_user"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)
        _insert_workflow(
            git_fs,
            "wf-ok",
            checkpoint=_checkpoint(next_step_index=0, pending_result=None, pending_step_id="step-1"),
        )
        monkeypatch.setattr(
            "worktree.cli.workflow.command.CliFailurePrompter.is_interactive",
            True,
        )
        monkeypatch.setattr(
            "worktree.cli.workflow.command.CliFailurePrompter.prompt_step_failure",
            lambda self, *args, **kwargs: FailurePromptDecision.RETRY,
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-ok", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Resuming workflow session 'wf-ok'..." in out

    def test_workflow_resume_loop_step_runtime_error(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "loop-wf",
            id="loop-wf",
            steps=[
                {"id": "step-1", "run": "echo hi"},
                {
                    "id": "loop-1",
                    "type": "loop",
                    "max_iterations": 2,
                    "until": ["true"],
                    "do": [{"id": "s1", "run": "echo loop"}],
                },
            ],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)
        _insert_workflow(
            git_fs,
            "wf-loop",
            workflow_name="loop-wf",
            checkpoint=_checkpoint(next_step_index=0, pending_result=None, pending_step_id="step-1"),
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-loop", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out
        assert "Engine.resume does not execute loop steps." in out

    def test_workflow_resume_execution_failure_outcome(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "fail-wf",
            id="fail-wf",
            steps=[{"id": "step-1", "run": "exit 1", "on_failure": "abort"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)
        _insert_workflow(
            git_fs,
            "wf-fail",
            workflow_name="fail-wf",
            checkpoint=_checkpoint(next_step_index=0, pending_result=None, pending_step_id="step-1"),
        )

        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-fail", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Workflow Resume Failed" in out

    def test_workflow_resume_paused_outcome(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        _insert_workflow(git_fs, "wf-pause", checkpoint=_checkpoint())

        paused_outcome = RunOutcome(
            status=RunStatus.PAUSED,
            session_id="wf-pause",
            step_results=[],
            sandbox_path=git_fs.base_path,
        )
        monkeypatch.setattr(
            "worktree.cli.workflow.command.Engine.resume",
            lambda *args, **kwargs: paused_outcome,
        )
        with pytest.raises(typer.Exit) as exc_info:
            workflow_resume_command("wf-pause", cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0


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

    def test_task_session_id_refused_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        runs_db = RunsDb(git_fs.base_path)
        runs_db.create(
            session_id="task-session-2", blueprint_name="sample-task", kind=BlueprintKind.TASK, status=RunStatus.RUNNING
        )
        runs_db.save_pause("task-session-2", _checkpoint().model_dump_json(), "paused")

        result = runner.invoke(app, ["workflow", "resume", "task-session-2"])
        assert result.exit_code == 1
        assert "Workflow Resume Failed" in result.stdout
        assert "Workflow session 'task-session-2' not found." in result.stdout
