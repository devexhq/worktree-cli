"""Unit tests for the Engine.resume facade."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintDefinition, BlueprintKind
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunsDb, RunStatus
from worktree.core.engine import Engine, EngineResumeError, EngineResumeStatus, EngineRuntimeError, ResumableRun
from worktree.core.runtime import RunCheckpoint, RunContext, RunOutcome
from worktree.core.step import LoopStepBlock, StepDefinition, StepResult, StepType


def _cmd_step(step_id: str, command: str = "echo ok") -> StepDefinition:
    return StepDefinition(id=step_id, type=StepType.COMMAND, command=command)


def _ok_result(step_id: str) -> StepResult:
    return StepResult(
        step_id=step_id,
        status="completed",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.01,
    )


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


def _checkpoint(**overrides: object) -> RunCheckpoint:
    payload: dict[str, object] = {
        "next_step_index": 1,
        "step_results": [_ok_result("setup")],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": True,
        "agent": "copilot",
        "inputs": {"name": "demo"},
        "pending_step_id": "publish",
        "diagnostic": "Step 'publish' failed: boom",
        "pending_result": _failed_result(),
    }
    payload.update(overrides)
    return RunCheckpoint.model_validate(payload)


def _task_blueprint(*, name: str = "lint", loop: bool = False) -> Blueprint:
    steps: list[Any] = [_cmd_step("setup"), _cmd_step("publish", "exit 1"), _cmd_step("later")]
    if loop:
        steps.append(
            LoopStepBlock.model_validate(
                {
                    "id": "retry",
                    "type": "loop",
                    "until": ["steps.unit.exit_code == 0"],
                    "do": [{"id": "unit", "run": "pytest"}],
                }
            )
        )
    return Blueprint(
        BlueprintDefinition(
            kind=BlueprintKind.WORKFLOW if loop else BlueprintKind.TASK,
            name=name,
            use_sandbox=False,
            steps=steps,
        )
    )


def _workflow_blueprint(*, name: str = "ship") -> Blueprint:
    return Blueprint(
        BlueprintDefinition(
            kind=BlueprintKind.WORKFLOW,
            name=name,
            use_sandbox=False,
            steps=[_cmd_step("setup"), _cmd_step("publish", "exit 1"), _cmd_step("later")],
        )
    )


def _seed_paused_task(fs: FileSystem, session_id: str, checkpoint: RunCheckpoint, *, name: str = "lint") -> None:
    db = RunsDb(fs.base_path)
    db.create(session_id, blueprint_name=name, kind=BlueprintKind.TASK, status=RunStatus.RUNNING)
    db.save_pause(session_id, checkpoint.model_dump_json(), checkpoint.diagnostic)


def _seed_paused_workflow(fs: FileSystem, session_id: str, checkpoint: RunCheckpoint, *, name: str = "ship") -> None:
    db = RunsDb(fs.base_path)
    db.create(session_id, blueprint_name=name, kind=BlueprintKind.WORKFLOW, branch_name="", status=RunStatus.RUNNING)
    db.save_pause(session_id, checkpoint.model_dump_json(), checkpoint.diagnostic)


def test_resume_rebuilds_context_from_checkpoint(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    checkpoint = _checkpoint()
    _seed_paused_task(fs, "task_resume", checkpoint)
    observer = MagicMock()
    expected = RunOutcome(status=RunStatus.COMPLETED, step_results=[], sandbox_path=fs.base_path)
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return expected

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    outcome = Engine(fs.base_path).resume(
        "task_resume",
        blueprint=_task_blueprint(),
        observer=observer,
        non_interactive=True,
        failure_prompter=None,
    )

    assert outcome == expected.model_copy(update={"session_id": "task_resume"})
    context = captured["context"]
    assert [step.id for step in context.steps] == ["setup", "publish", "later"]
    assert context.cwd == fs.base_path.resolve()
    assert context.use_sandbox is False
    assert context.keep is True
    assert context.agent == "copilot"
    assert context.observer is observer
    assert context.inputs == {"name": "demo"}
    assert context.non_interactive is True
    assert context.failure_prompter is None
    assert context.pause_store is not None
    assert context.resume_from == checkpoint


def test_resume_finalizes_task_row(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    _seed_paused_task(fs, "task_done", _checkpoint())
    monkeypatch.setattr(
        "worktree.core.engine.engine.run_steps",
        lambda _context: RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path),
    )

    outcome = Engine(fs.base_path).resume("task_done", blueprint=_task_blueprint())

    assert outcome.ok
    record = RunsDb(fs.base_path).get("task_done")
    assert record is not None
    assert record.status is RunStatus.COMPLETED
    assert record.completed_at is not None


def test_resume_finalizes_workflow_row(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    _seed_paused_workflow(fs, "workflow_done", _checkpoint())
    monkeypatch.setattr(
        "worktree.core.engine.engine.run_steps",
        lambda _context: RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path),
    )

    outcome = Engine(fs.base_path).resume("workflow_done", blueprint=_workflow_blueprint())

    assert outcome.ok
    record = RunsDb(fs.base_path).get("workflow_done")
    assert record is not None
    assert record.blueprint_name == "ship"
    assert record.status is RunStatus.COMPLETED


def test_resume_not_found(fs: FileSystem) -> None:
    with pytest.raises(EngineResumeError, match=r"Session 'missing' not found\.") as exc_info:
        Engine(fs.base_path).resume("missing", blueprint=_task_blueprint())

    assert exc_info.value.status is EngineResumeStatus.NOT_FOUND


def test_resume_omitted_blueprint_not_found(fs: FileSystem) -> None:
    with pytest.raises(EngineResumeError, match=r"Session 'missing' not found\.") as exc_info:
        Engine(fs.base_path).resume("missing")

    assert exc_info.value.status is EngineResumeStatus.NOT_FOUND


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.RUNNING, RunStatus.CANCELLED])
def test_resume_wrong_status(fs: FileSystem, status: RunStatus) -> None:
    RunsDb(fs.base_path).create("task_wrong", blueprint_name="lint", kind=BlueprintKind.TASK, status=status)

    with pytest.raises(EngineResumeError) as exc_info:
        Engine(fs.base_path).resume("task_wrong", blueprint=_task_blueprint())

    assert exc_info.value.status is EngineResumeStatus.WRONG_STATUS
    assert str(exc_info.value) == f"Cannot resume session 'task_wrong': status is '{status.value}' (expected paused)."


def test_resume_corrupt_checkpoint(fs: FileSystem) -> None:
    db = RunsDb(fs.base_path)
    db.create("task_bad", blueprint_name="lint", kind=BlueprintKind.TASK, status=RunStatus.RUNNING)
    db.save_pause("task_bad", "{nope", "paused")

    with pytest.raises(EngineResumeError, match="checkpoint is missing or corrupt") as exc_info:
        Engine(fs.base_path).resume("task_bad", blueprint=_task_blueprint())

    assert exc_info.value.status is EngineResumeStatus.CORRUPT_CHECKPOINT


def test_resume_missing_sandbox(fs: FileSystem) -> None:
    missing = fs.base_path / "does-not-exist"
    _seed_paused_task(fs, "task_box", _checkpoint(use_sandbox=True, sandbox_path=str(missing)))

    with pytest.raises(EngineResumeError) as exc_info:
        Engine(fs.base_path).resume("task_box", blueprint=_task_blueprint())

    assert exc_info.value.status is EngineResumeStatus.MISSING_SANDBOX
    assert str(exc_info.value) == f"Cannot resume session 'task_box': sandbox path '{missing}' no longer exists."


def test_resume_pending_step_mismatch_is_corrupt(fs: FileSystem) -> None:
    _seed_paused_task(fs, "task_pending", _checkpoint(pending_step_id="ghost"))

    with pytest.raises(EngineResumeError, match="checkpoint is missing or corrupt") as exc_info:
        Engine(fs.base_path).resume("task_pending", blueprint=_task_blueprint())

    assert exc_info.value.status is EngineResumeStatus.CORRUPT_CHECKPOINT
    record = RunsDb(fs.base_path).get("task_pending")
    assert record is not None
    assert record.status is RunStatus.PAUSED


def test_resume_rejects_loop_steps_after_classification(fs: FileSystem) -> None:
    _seed_paused_workflow(fs, "workflow_loop", _checkpoint())

    with pytest.raises(EngineRuntimeError, match=r"Engine\.resume does not execute loop steps\."):
        Engine(fs.base_path).resume("workflow_loop", blueprint=_task_blueprint(loop=True, name="ship"))

    record = RunsDb(fs.base_path).get("workflow_loop")
    assert record is not None
    assert record.status is RunStatus.PAUSED


def test_resume_omitted_blueprint_loads_from_catalog(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    fs.create_task_file(
        "lint",
        use_sandbox=False,
        steps=[
            {"id": "setup", "run": "echo setup"},
            {"id": "publish", "run": "exit 1"},
            {"id": "later", "run": "echo later"},
        ],
    )
    scan_and_index_catalog(cwd=fs.base_path)
    _seed_paused_task(fs, "task_catalog", _checkpoint())
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    outcome = Engine(fs.base_path).resume("task_catalog")

    assert outcome.ok
    assert [step.id for step in captured["context"].steps] == ["setup", "publish", "later"]
    assert captured["context"].resume_from is not None


def test_resume_omitted_blueprint_missing_catalog(fs: FileSystem) -> None:
    _seed_paused_task(fs, "task_gone", _checkpoint(), name="missing-task")

    with pytest.raises(EngineResumeError, match="blueprint 'missing-task' not found") as exc_info:
        Engine(fs.base_path).resume("task_gone")

    assert exc_info.value.status is EngineResumeStatus.FAILED


def test_resume_mark_running_failure_warns(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    _seed_paused_task(fs, "task_mark", _checkpoint())
    expected = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path, warnings=["step note"])
    monkeypatch.setattr("worktree.core.engine.engine.run_steps", lambda _context: expected)
    monkeypatch.setattr(
        "worktree.core.engine.engine._DbPauseStore.clear_pause",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("locked")),
    )

    outcome = Engine(fs.base_path).resume("task_mark", blueprint=_task_blueprint())

    assert outcome is not expected
    assert outcome.warnings[0] == "step note"
    assert any(warning.startswith("Failed to update run status in database:") for warning in outcome.warnings)


def test_resume_finalize_failure_warns(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    _seed_paused_task(fs, "task_final", _checkpoint())
    expected = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)
    monkeypatch.setattr("worktree.core.engine.engine.run_steps", lambda _context: expected)
    monkeypatch.setattr(
        "worktree.core.engine.engine._DbPauseStore.finalize",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("locked")),
    )

    outcome = Engine(fs.base_path).resume("task_final", blueprint=_task_blueprint())

    assert any(warning.startswith("Failed to update run status in database:") for warning in outcome.warnings)
    record = RunsDb(fs.base_path).get("task_final")
    assert record is not None
    assert record.status is RunStatus.RUNNING


def test_resumable_run_load_is_resumable(fs: FileSystem) -> None:
    checkpoint = _checkpoint()
    _seed_paused_task(fs, "task_ready", checkpoint)

    handle = ResumableRun.load("task_ready", _task_blueprint(), cwd=fs.base_path)

    assert handle.is_resumable is True
    assert handle.status is EngineResumeStatus.OK
    assert handle.checkpoint == checkpoint
    assert [step.id for step in handle.steps] == ["setup", "publish", "later"]


def test_resumable_run_load_not_resumable(fs: FileSystem) -> None:
    handle = ResumableRun.load("missing", _task_blueprint(), cwd=fs.base_path)

    assert handle.is_resumable is False
    assert handle.status is EngineResumeStatus.NOT_FOUND
    assert str(handle) == "Session 'missing' not found."

    with pytest.raises(EngineResumeError, match=r"Session 'missing' not found\.") as exc_info:
        handle.ready()

    assert exc_info.value.status is EngineResumeStatus.NOT_FOUND
