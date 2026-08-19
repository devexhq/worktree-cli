"""Unit tests for the Engine.run facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintDefinition, BlueprintKind
from worktree.core.db import RunsRepository, RunStatus
from worktree.core.engine import Engine, EngineInputError, EngineRuntimeError, RunRequest
from worktree.core.inputs import InputType, ParameterInput
from worktree.core.runtime import RunContext, RunOutcome
from worktree.core.step import LoopStepBlock, StepDefinition, StepType


def _cmd_step(step_id: str = "s1") -> StepDefinition:
    return StepDefinition(
        id=step_id,
        type=StepType.COMMAND,
        command="echo ok",
    )


def _task_blueprint(
    *,
    name: str = "lint",
    use_sandbox: bool = True,
    steps: list[StepDefinition] | None = None,
) -> Blueprint:
    return Blueprint(
        BlueprintDefinition(
            kind=BlueprintKind.TASK,
            name=name,
            use_sandbox=use_sandbox,
            steps=list(steps) if steps is not None else [_cmd_step()],
        )
    )


def _workflow_blueprint(*, name: str = "ship", loop: bool = False) -> Blueprint:
    steps: list[Any] = [_cmd_step("ruff")]
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
            kind=BlueprintKind.WORKFLOW,
            name=name,
            use_sandbox=False,
            steps=steps,
        )
    )


def test_construct_resolves_cwd(tmp_path: Path) -> None:
    engine = Engine(tmp_path)

    assert engine.cwd == tmp_path.resolve()
    assert not hasattr(Engine, "spec")


def test_run_delegates_to_run_steps(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    steps = [_cmd_step("one"), _cmd_step("two")]
    blueprint = _task_blueprint(steps=steps, use_sandbox=True)
    observer = MagicMock()
    expected = RunOutcome(status=RunStatus.COMPLETED, step_results=[], sandbox_path=fs.base_path)
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return expected

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    outcome = Engine(fs.base_path).run(
        blueprint,
        RunRequest(
            use_sandbox=True,
            keep=True,
            agent="copilot",
            session_id="task_demo",
            observer=observer,
            inputs={"message": "hi"},
            non_interactive=True,
            failure_prompter=None,
        ),
    )

    assert outcome == expected.model_copy(update={"session_id": "task_demo"})
    context = captured["context"]
    assert context.steps == steps
    assert context.cwd == fs.base_path.resolve()
    assert context.use_sandbox is True
    assert context.keep is True
    assert context.agent == "copilot"
    assert context.observer is observer
    assert context.inputs == {"message": "hi"}
    assert context.non_interactive is True
    assert context.failure_prompter is None
    assert context.pause_store is not None
    assert context.resume_from is None


@pytest.mark.parametrize(
    ("caller_use_sandbox", "definition_use_sandbox", "expected"),
    [
        (None, True, True),
        (None, False, False),
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_run_use_sandbox_logic(
    monkeypatch: pytest.MonkeyPatch,
    fs: FileSystem,
    caller_use_sandbox: bool | None,
    definition_use_sandbox: bool,
    expected: bool,
) -> None:
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    Engine(fs.base_path).run(
        _task_blueprint(use_sandbox=definition_use_sandbox),
        RunRequest(use_sandbox=caller_use_sandbox, session_id="task_sandbox"),
    )

    assert captured["context"].use_sandbox is expected


def test_run_persists_completed_task_row(fs: FileSystem) -> None:
    outcome = Engine(fs.base_path).run(
        _task_blueprint(use_sandbox=False),
        RunRequest(use_sandbox=False, session_id="task_persist"),
    )

    assert outcome.ok
    record = RunsRepository(fs.base_path).get("task_persist")
    assert record is not None
    assert record.blueprint_name == "lint"
    assert record.kind == BlueprintKind.TASK
    assert record.status is RunStatus.COMPLETED
    assert record.completed_at is not None


def test_run_persists_workflow_row_with_empty_branch(fs: FileSystem) -> None:
    outcome = Engine(fs.base_path).run(
        _workflow_blueprint(),
        RunRequest(use_sandbox=False, session_id="workflow_persist"),
    )

    assert outcome.ok
    record = RunsRepository(fs.base_path).get("workflow_persist")
    assert record is not None
    assert record.blueprint_name == "ship"
    assert record.kind == BlueprintKind.WORKFLOW
    assert record.branch_name == ""
    assert record.status is RunStatus.COMPLETED


def test_run_rejects_loop_steps_before_insert(fs: FileSystem) -> None:
    with pytest.raises(EngineRuntimeError, match=r"Engine\.run does not execute loop steps\."):
        Engine(fs.base_path).run(_workflow_blueprint(loop=True), RunRequest(session_id="workflow_loop"))

    assert RunsRepository(fs.base_path).get("workflow_loop") is None


def test_insert_failure_warns_and_still_runs(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)
    monkeypatch.setattr("worktree.core.engine.engine.RunsRepository.create", boom)

    outcome = Engine(fs.base_path).run(_task_blueprint(), RunRequest(session_id="task_insert_fail"))

    assert captured["context"].pause_store is None
    assert any(warning.startswith("Failed to record run start in database:") for warning in outcome.warnings)
    assert RunsRepository(fs.base_path).get("task_insert_fail") is None


def test_update_failure_warns_and_returns_outcome(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    expected = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path, warnings=["step note"])

    monkeypatch.setattr(
        "worktree.core.engine.engine.run_steps",
        lambda _context: expected,
    )
    monkeypatch.setattr(
        "worktree.core.engine.engine._DbPauseStore.finalize",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("locked")),
    )

    outcome = Engine(fs.base_path).run(_task_blueprint(), RunRequest(session_id="task_update_fail"))

    assert outcome is not expected
    assert outcome.warnings[0] == "step note"
    assert any(warning.startswith("Failed to update run status in database:") for warning in outcome.warnings)
    record = RunsRepository(fs.base_path).get("task_update_fail")
    assert record is not None
    assert record.status is RunStatus.RUNNING


def test_omitted_session_id_uses_kind_prefix(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    monkeypatch.setattr(
        "worktree.core.engine.engine.run_steps",
        lambda _context: RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path),
    )

    outcome = Engine(fs.base_path).run(_task_blueprint(use_sandbox=False), RunRequest(use_sandbox=False))

    records = RunsRepository(fs.base_path).list()
    assert len(records) == 1
    assert records[0].session_id.startswith("task_")
    assert len(records[0].session_id) == len("task_") + 8
    assert outcome.session_id == records[0].session_id


def _input_blueprint() -> Blueprint:
    return Blueprint(
        BlueprintDefinition(
            kind=BlueprintKind.TASK,
            name="commit",
            use_sandbox=False,
            inputs={
                "message": ParameterInput(type=InputType.STRING, required=True, aliases=["-m"]),
                "allow_empty": ParameterInput(type=InputType.BOOLEAN, default=False),
            },
            steps=[_cmd_step()],
        )
    )


def test_run_without_request_uses_defaults(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    outcome = Engine(fs.base_path).run(_task_blueprint(use_sandbox=False))

    assert captured["context"].inputs == {}
    assert outcome.session_id is not None
    assert outcome.session_id.startswith("task_")


def test_run_applies_input_defaults(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    Engine(fs.base_path).run(_input_blueprint(), RunRequest(inputs={"message": "ship it"}))

    assert captured["context"].inputs == {"message": "ship it", "allow_empty": False}


def test_run_parses_cli_args(monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

    monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

    Engine(fs.base_path).run(_input_blueprint(), RunRequest(cli_args=["-m", "from argv"]))

    assert captured["context"].inputs == {"message": "from argv", "allow_empty": False}


def test_run_missing_required_input_raises_before_insert(fs: FileSystem) -> None:
    with pytest.raises(EngineInputError, match="Missing required input 'message'") as exc_info:
        Engine(fs.base_path).run(_input_blueprint())

    assert exc_info.value.result.missing == ["message"]
    assert RunsRepository(fs.base_path).list() == []


def test_run_invalid_input_raises_before_insert(fs: FileSystem) -> None:
    with pytest.raises(EngineInputError, match="expects an integer") as exc_info:
        Engine(fs.base_path).run(
            Blueprint(
                BlueprintDefinition(
                    kind=BlueprintKind.TASK,
                    name="count",
                    use_sandbox=False,
                    inputs={"n": ParameterInput(type=InputType.INTEGER, required=True)},
                    steps=[_cmd_step()],
                )
            ),
            RunRequest(cli_args=["-i", "n=nope"]),
        )

    assert exc_info.value.result.errors
    assert RunsRepository(fs.base_path).list() == []
