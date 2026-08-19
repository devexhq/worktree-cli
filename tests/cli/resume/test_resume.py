"""Comprehensive unit and CLI integration tests for ``wt resume``."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem
from worktree.cli import app
from worktree.core.blueprint import BlueprintKind, BlueprintResumeService
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunsRepository, RunStatus
from worktree.core.runtime import FailurePromptDecision, RunCheckpoint
from worktree.core.step import StepResult

runner = CliRunner()


def _failed_result(step_id: str = "step-2") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="step failed",
        duration_seconds=0.01,
        error_message="step execution error",
    )


def _ok_result(step_id: str = "step-1") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="completed",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.01,
    )


def _checkpoint(**overrides: object) -> RunCheckpoint:
    payload: dict[str, object] = {
        "next_step_index": 1,
        "step_results": [_ok_result("step-1")],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": False,
        "pending_step_id": "step-2",
        "diagnostic": "",
        "pending_result": None,
    }
    payload.update(overrides)
    return RunCheckpoint.model_validate(payload)


def _seed_paused_run(
    fs_path,
    session_id: str,
    blueprint_name: str,
    kind: BlueprintKind,
    checkpoint: RunCheckpoint | None = None,
    *,
    status: RunStatus = RunStatus.PAUSED,
) -> None:
    db = RunsRepository(fs_path)
    db.create(
        session_id=session_id,
        blueprint_name=blueprint_name,
        kind=kind,
        branch_name="wt/resume",
        status=RunStatus.RUNNING,
    )
    if status is RunStatus.PAUSED:
        raw = checkpoint.model_dump_json() if checkpoint is not None else _checkpoint().model_dump_json()
        db.save_pause(session_id, raw, "paused")
    else:
        db.update_status(session_id, status)


@pytest.fixture
def mock_interactive_prompter(monkeypatch: pytest.MonkeyPatch):
    """Simulate an interactive user choosing to RETRY the paused step."""
    monkeypatch.setattr(
        "worktree.core.blueprint.services.resume.CliFailurePrompter.is_interactive",
        True,
    )
    monkeypatch.setattr(
        "worktree.core.blueprint.services.resume.CliFailurePrompter.prompt_step_failure",
        lambda self, *args, **kwargs: FailurePromptDecision.RETRY,
    )


def test_blueprint_resume_service_resumes_task(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify BlueprintResumeService successfully resumes a paused task session."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "sample-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-res-1", "sample-task", BlueprintKind.TASK)

    outcome = BlueprintResumeService(session_id="task-res-1", cwd=fs.base_path).execute()
    assert outcome.ok
    assert outcome.run_record is not None
    assert outcome.run_record.status == RunStatus.COMPLETED
    assert outcome.run_record.kind == BlueprintKind.TASK

    record = RunsRepository(fs.base_path).get("task-res-1")
    assert record is not None
    assert record.status == RunStatus.COMPLETED


def test_blueprint_resume_service_resumes_workflow(
    git_fs: GitFileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify BlueprintResumeService successfully resumes a paused workflow session."""
    git_fs.init_repo()
    monkeypatch.chdir(git_fs.base_path)
    git_fs.create_workflow_file(
        "deploy-wf",
        steps=[
            {"id": "step-1", "run": "echo wf1"},
            {"id": "step-2", "run": "echo wf2", "on_failure": "prompt_user"},
        ],
    )
    scan_and_index_catalog(cwd=git_fs.base_path)
    _seed_paused_run(git_fs.base_path, "wf-res-1", "deploy-wf", BlueprintKind.WORKFLOW)

    outcome = BlueprintResumeService(session_id="wf-res-1", cwd=git_fs.base_path).execute()
    assert outcome.ok
    assert outcome.run_record is not None
    assert outcome.run_record.status == RunStatus.COMPLETED
    assert outcome.run_record.kind == BlueprintKind.WORKFLOW

    record = RunsRepository(git_fs.base_path).get("wf-res-1")
    assert record is not None
    assert record.status == RunStatus.COMPLETED


def test_blueprint_resume_service_auto_resumes_latest(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify BlueprintResumeService auto-picks the most recent paused run when session_id is omitted."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "task-auto",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo auto1"},
            {"id": "step-2", "run": "echo auto2", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-old", "task-auto", BlueprintKind.TASK)
    _seed_paused_run(fs.base_path, "task-new", "task-auto", BlueprintKind.TASK)

    outcome = BlueprintResumeService(cwd=fs.base_path).execute()
    assert outcome.ok
    assert outcome.run_record is not None
    assert outcome.run_record.session_id == "task-new"
    assert outcome.run_record.status == RunStatus.COMPLETED


def test_blueprint_resume_service_no_paused_session_fails(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify BlueprintResumeService returns failure outcome when no paused session exists."""
    monkeypatch.chdir(fs.base_path)
    outcome = BlueprintResumeService(cwd=fs.base_path).execute()
    assert not outcome.ok
    assert outcome.run_record is None
    assert any("No paused session found to resume." in err for err in outcome.errors)


def test_resume_cli_explicit_session_task(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify CLI 'wt resume <session_id>' resumes an explicit task run."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "cli-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-explicit-1", "cli-task", BlueprintKind.TASK)

    result = runner.invoke(app, ["resume", "task-explicit-1"])
    assert result.exit_code == 0
    assert "Resuming session 'task-explicit-1'..." in result.output
    assert "Task Run Completed:" in result.output


def test_resume_cli_explicit_session_workflow(
    git_fs: GitFileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify CLI 'wt resume <session_id>' resumes an explicit workflow run."""
    git_fs.init_repo()
    monkeypatch.chdir(git_fs.base_path)
    git_fs.create_workflow_file(
        "cli-wf",
        steps=[
            {"id": "step-1", "run": "echo wf1"},
            {"id": "step-2", "run": "echo wf2", "on_failure": "prompt_user"},
        ],
    )
    scan_and_index_catalog(cwd=git_fs.base_path)
    _seed_paused_run(git_fs.base_path, "wf-explicit-1", "cli-wf", BlueprintKind.WORKFLOW)

    result = runner.invoke(app, ["resume", "wf-explicit-1"])
    assert result.exit_code == 0
    assert "Resuming session 'wf-explicit-1'..." in result.output
    assert "Workflow Run Completed:" in result.output


def test_resume_cli_auto_resumes_latest_paused(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
    mock_interactive_prompter: None,
) -> None:
    """Verify CLI 'wt resume' with no arguments auto-resumes the latest paused session."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "latest-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-latest-1", "latest-task", BlueprintKind.TASK)

    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 0
    assert "Resuming latest paused session 'task-latest-1' (latest-task)..." in result.output
    assert "Task Run Completed:" in result.output


def test_resume_cli_no_paused_session_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' exits 1 when no paused session exists."""
    monkeypatch.chdir(fs.base_path)
    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output
    assert "No paused session found to resume." in result.output


def test_resume_cli_non_existent_session_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume <invalid_id>' exits 1 with not found message."""
    monkeypatch.chdir(fs.base_path)
    result = runner.invoke(app, ["resume", "nonexistent-id"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output
    assert "Session 'nonexistent-id' not found." in result.output


def test_resume_cli_wrong_status_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' fails when session is in non-paused status."""
    monkeypatch.chdir(fs.base_path)
    _seed_paused_run(fs.base_path, "task-running", "sample-task", BlueprintKind.TASK, status=RunStatus.RUNNING)

    result = runner.invoke(app, ["resume", "task-running"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output
    assert "Cannot resume session 'task-running': status is 'running' (expected paused)." in result.output


def test_resume_cli_missing_sandbox_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' fails when sandbox directory was deleted."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "sandbox-task",
        use_sandbox=False,
        steps=[{"id": "step-1", "run": "echo 1"}, {"id": "step-2", "run": "echo 2"}],
    )
    checkpoint = _checkpoint(sandbox_path="/tmp/nonexistent-sandbox-dir", use_sandbox=True)
    _seed_paused_run(fs.base_path, "task-bad-box", "sandbox-task", BlueprintKind.TASK, checkpoint=checkpoint)

    result = runner.invoke(app, ["resume", "task-bad-box"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output
    assert "sandbox path '/tmp/nonexistent-sandbox-dir' no longer exists." in result.output


def test_resume_cli_corrupt_checkpoint_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' fails cleanly on corrupt checkpoint JSON."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "corrupt-task",
        use_sandbox=False,
        steps=[{"id": "step-1", "run": "echo 1"}, {"id": "step-2", "run": "echo 2"}],
    )
    db = RunsRepository(fs.base_path)
    db.create(
        session_id="task-corrupt", blueprint_name="corrupt-task", kind=BlueprintKind.TASK, status=RunStatus.RUNNING
    )
    db.save_pause("task-corrupt", "not-valid-json", "paused")

    result = runner.invoke(app, ["resume", "task-corrupt"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output
    assert "checkpoint is missing or corrupt." in result.output


def test_resume_cli_paused_status_exits_0(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a resumed run that pauses again exits with code 0."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "pause-again-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo 1"},
            {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-pause-again", "pause-again-task", BlueprintKind.TASK)

    class _InterruptPrompter:
        is_interactive: bool = True

        def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
            raise KeyboardInterrupt

    monkeypatch.setattr(
        "worktree.core.blueprint.services.resume.CliFailurePrompter",
        lambda *args, **kwargs: _InterruptPrompter(),
    )

    outcome = BlueprintResumeService(session_id="task-pause-again", cwd=fs.base_path).execute()
    assert outcome.ok
    assert outcome.run_record is not None
    assert outcome.run_record.status == RunStatus.PAUSED


def test_resume_cli_step_failure_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' exits 1 when a resumed step aborts/fails."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "fail-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo 1"},
            {"id": "step-2", "run": "exit 1", "on_failure": "abort"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-fail-run", "fail-task", BlueprintKind.TASK)

    result = runner.invoke(app, ["resume", "task-fail-run", "--non-interactive"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output


def test_resume_cli_non_interactive_flag_aborts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --non-interactive flag prevents interactive prompting and aborts."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "non-int-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo 1"},
            {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-non-int", "non-int-task", BlueprintKind.TASK)

    result = runner.invoke(app, ["resume", "task-non-int", "--non-interactive"])
    assert result.exit_code == 1
    assert "Resume Failed" in result.output


def test_resume_cli_cancelled_status(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt resume' handles cancelled status cleanly."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "cancel-task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo 1"},
            {"id": "step-2", "run": "echo 2", "on_failure": "prompt_user"},
        ],
    )
    _seed_paused_run(fs.base_path, "task-cancel", "cancel-task", BlueprintKind.TASK)

    monkeypatch.setattr(
        "worktree.core.blueprint.services.resume.Engine.resume",
        lambda *args, **kwargs: type(
            "RunOutcome",
            (),
            {"ok": False, "status": RunStatus.CANCELLED, "error_message": "Cancelled by user.", "warnings": []},
        )(),
    )

    result = runner.invoke(app, ["resume", "task-cancel"])
    assert result.exit_code == 1
    assert "Resume Cancelled" in result.output
