"""Unit tests for the task run_task execution adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from worktree.core.db import RunStatus
from worktree.core.runtime import RunContext, RunOutcome
from worktree.core.step import StepDefinition, StepType
from worktree.core.task import run_task
from worktree.core.task.models import TaskDefinition


def _cmd_step(step_id: str = "s1") -> StepDefinition:
    return StepDefinition(
        id=step_id,
        type=StepType.COMMAND,
        command="echo ok",
    )


def test_run_task_delegates_to_run_steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    steps = [_cmd_step("one"), _cmd_step("two")]
    definition = TaskDefinition(name="demo", steps=steps, use_sandbox=True)
    observer = MagicMock()
    expected = RunOutcome(
        status=RunStatus.COMPLETED,
        step_results=[],
        sandbox_path=tmp_path,
    )
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return expected

    monkeypatch.setattr("worktree.core.task.services.runner.run_steps", fake_run_steps)

    outcome = run_task(
        definition,
        tmp_path,
        use_sandbox=True,
        keep=True,
        agent="copilot",
        observer=observer,
        inputs={"message": "hi"},
    )

    assert outcome is expected
    context = captured["context"]
    assert context.steps == steps
    assert context.cwd == tmp_path
    assert context.use_sandbox is True
    assert context.keep is True
    assert context.agent == "copilot"
    assert context.observer is observer
    assert context.inputs == {"message": "hi"}


@pytest.mark.parametrize(
    ("caller_use_sandbox", "definition_use_sandbox", "expected"),
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_run_task_use_sandbox_logic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caller_use_sandbox: bool,
    definition_use_sandbox: bool,
    expected: bool,
) -> None:
    definition = TaskDefinition(
        name="demo",
        steps=[_cmd_step()],
        use_sandbox=definition_use_sandbox,
    )
    captured: dict[str, RunContext] = {}

    def fake_run_steps(context: RunContext) -> RunOutcome:
        captured["context"] = context
        return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=tmp_path)

    monkeypatch.setattr("worktree.core.task.services.runner.run_steps", fake_run_steps)

    run_task(definition, tmp_path, use_sandbox=caller_use_sandbox)

    assert captured["context"].use_sandbox is expected
