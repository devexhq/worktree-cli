"""Unit tests for the task run_task execution adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers import make_cmd_step
from worktree.core.db import RunStatus
from worktree.core.runtime import RunContext, RunOutcome
from worktree.core.task import run_task
from worktree.core.task.models import TaskDefinition


class TaskRunnerTests:
    """Unit tests for run_task delegation and sandbox resolution logic."""

    def test_run_task_delegates_to_run_steps(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        steps = [make_cmd_step(step_id="one"), make_cmd_step(step_id="two")]
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
            non_interactive=True,
            failure_prompter=None,
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
        assert context.non_interactive is True
        assert context.failure_prompter is None

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
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caller_use_sandbox: bool,
        definition_use_sandbox: bool,
        expected: bool,
    ) -> None:
        definition = TaskDefinition(
            name="demo",
            steps=[make_cmd_step()],
            use_sandbox=definition_use_sandbox,
        )
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=tmp_path)

        monkeypatch.setattr("worktree.core.task.services.runner.run_steps", fake_run_steps)

        run_task(definition, tmp_path, use_sandbox=caller_use_sandbox)

        assert captured["context"].use_sandbox is expected
