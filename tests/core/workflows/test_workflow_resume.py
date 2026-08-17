"""Tests for durable workflow pause/resume."""

from __future__ import annotations

import pytest

from tests.helpers import GitFileSystem
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunStatus, WorkflowsDb
from worktree.core.runtime import FailurePromptDecision, RunCheckpoint
from worktree.core.step import StepDefinition, StepResult
from worktree.core.workflows.models import WorkflowResumeStatus
from worktree.core.workflows.services.resume import resume_workflow


class _ScriptedPrompter:
    def __init__(self, decisions: list[FailurePromptDecision]) -> None:
        self.decisions = list(decisions)
        self.calls = 0

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        self.calls += 1
        return self.decisions.pop(0)


def _failed_result(step_id: str = "publish") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="nope",
        duration_seconds=0.01,
        error_message="boom",
    )


def _ok_result(step_id: str) -> StepResult:
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
        "step_results": [_ok_result("setup")],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": False,
        "inputs": {"name": "demo"},
        "pending_step_id": "publish",
        "diagnostic": "Step 'publish' failed: boom",
        "pending_result": _failed_result(),
    }
    payload.update(overrides)
    return RunCheckpoint.model_validate(payload)


def _seed_paused_workflow(git_fs: GitFileSystem, session_id: str, checkpoint: RunCheckpoint) -> None:
    git_fs.create_workflow_file(
        "resume-demo",
        id="resume-demo",
        steps=[
            {"id": "setup", "run": "echo setup"},
            {"id": "publish", "run": "exit 1", "on_failure": "prompt_user"},
            {"id": "later", "run": "echo later"},
        ],
    )
    scan_and_index_catalog(cwd=git_fs.base_path)
    db = WorkflowsDb(git_fs.base_path)
    db.insert(session_id=session_id, workflow_name="resume-demo", branch_name="wt/resume")
    db.save_pause(session_id, checkpoint.model_dump_json(), checkpoint.diagnostic)


def test_resume_workflow_happy_path_skips_completed(
    git_fs: GitFileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_fs.init_repo()
    _seed_paused_workflow(git_fs, "wf-ok", _checkpoint())
    prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])
    executed: list[str] = []

    def fake_execute(step: StepDefinition, sandbox_path: object, context: object = None) -> StepResult:
        executed.append(step.id)
        return _ok_result(step.id)

    monkeypatch.setattr("worktree.core.runtime.engine.execute_step", fake_execute)

    result = resume_workflow(
        "wf-ok",
        git_fs.base_path,
        failure_prompter=prompter,
    )

    assert result.ok is True
    assert prompter.calls == 1
    assert executed == ["later"]
    row = WorkflowsDb(git_fs.base_path).get("wf-ok")
    assert row is not None
    assert row.status is RunStatus.COMPLETED


def test_resume_workflow_wrong_status(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    WorkflowsDb(git_fs.base_path).insert(
        session_id="wf-done",
        workflow_name="resume-demo",
        branch_name="wt/resume",
        status=RunStatus.COMPLETED,
    )
    result = resume_workflow("wf-done", git_fs.base_path)
    assert result.status is WorkflowResumeStatus.WRONG_STATUS
    assert result.errors == ["Cannot resume session 'wf-done': status is 'completed' (expected paused)."]


def test_resume_workflow_not_found(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    result = resume_workflow("missing", git_fs.base_path)
    assert result.status is WorkflowResumeStatus.NOT_FOUND
    assert result.errors == ["Workflow session 'missing' not found."]


def test_resume_workflow_missing_sandbox(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    missing = git_fs.base_path / "does-not-exist"
    _seed_paused_workflow(
        git_fs,
        "wf-box",
        _checkpoint(use_sandbox=True, sandbox_path=str(missing)),
    )
    result = resume_workflow("wf-box", git_fs.base_path)
    assert result.status is WorkflowResumeStatus.MISSING_SANDBOX
    assert result.errors == [f"Cannot resume session 'wf-box': sandbox path '{missing}' no longer exists."]


def test_resume_workflow_corrupt_checkpoint(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    db = WorkflowsDb(git_fs.base_path)
    db.insert(session_id="wf-bad", workflow_name="resume-demo", branch_name="wt/resume")
    db.save_pause("wf-bad", "{nope", "paused")
    result = resume_workflow("wf-bad", git_fs.base_path)
    assert result.status is WorkflowResumeStatus.CORRUPT_CHECKPOINT
    assert result.errors == ["Cannot resume session 'wf-bad': checkpoint is missing or corrupt."]


def test_resume_workflow_reprompts_pending_step(git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    git_fs.init_repo()
    _seed_paused_workflow(git_fs, "wf-retry", _checkpoint())
    prompter = _ScriptedPrompter([FailurePromptDecision.RETRY])
    monkeypatch.setattr(
        "worktree.core.runtime.engine.execute_step",
        lambda step, sandbox_path, context=None: _ok_result(step.id),
    )
    result = resume_workflow("wf-retry", git_fs.base_path, failure_prompter=prompter)
    assert result.ok is True
    assert prompter.calls == 1
