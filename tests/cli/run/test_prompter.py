"""Unit tests for DispatcherFailurePrompter and prompt formatting."""

from __future__ import annotations

import io
import json

import pytest

from tests.helpers import make_dispatcher_with_buffer
from worktree.cli.run.prompter import DispatcherFailurePrompter
from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.cli.ui.events import PromptEvent, PromptOption
from worktree.cli.ui.formatters.events.prompt import PromptFormatter
from worktree.core.runtime.models import (
    FailurePromptDecision,
    LoopPromptDecision,
)
from worktree.core.step import LoopStepBlock, StepDefinition, StepResult


class TestDispatcherFailurePrompter:
    """Tests for DispatcherFailurePrompter decision parsing and prompt interactions."""

    @pytest.mark.parametrize(
        ("raw_input", "expected"),
        [
            pytest.param("r", FailurePromptDecision.RETRY, id="short_retry"),
            pytest.param("retry", FailurePromptDecision.RETRY, id="full_retry"),
            pytest.param("c", FailurePromptDecision.CONTINUE, id="short_continue"),
            pytest.param("continue", FailurePromptDecision.CONTINUE, id="full_continue"),
            pytest.param("a", FailurePromptDecision.ABORT, id="short_abort"),
            pytest.param("abort", FailurePromptDecision.ABORT, id="full_abort"),
            pytest.param("  R  ", FailurePromptDecision.RETRY, id="whitespace_and_uppercase_retry"),
        ],
    )
    def test_prompt_step_failure_terminal_valid_decisions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        raw_input: str,
        expected: FailurePromptDecision,
    ) -> None:
        dispatcher, buf = make_dispatcher_with_buffer(force_terminal=True)
        prompter = DispatcherFailurePrompter(dispatcher, kind="task")

        step = StepDefinition(id="step_1", name="Build Step", run="make build")
        result = StepResult(
            step_id="step_1",
            status="failed",
            exit_code=2,
            stdout="",
            stderr="compile error",
            duration_seconds=0.5,
        )

        monkeypatch.setattr("builtins.input", lambda _: raw_input)
        decision = prompter.prompt_step_failure(
            step=step,
            result=result,
            diagnostic="Compilation failed on line 10",
        )

        assert decision == expected
        rendered = buf.getvalue()
        assert "Step 'Build Step' failed (exit code 2)." in rendered
        assert "Compilation failed on line 10" in rendered
        assert "Task paused waiting for user input." in rendered
        assert "Options:" in rendered

    def test_prompt_step_failure_invalid_then_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dispatcher, buf = make_dispatcher_with_buffer(force_terminal=True)
        prompter = DispatcherFailurePrompter(dispatcher, kind="task")

        step = StepDefinition(id="step_1", run="make")
        result = StepResult(step_id="step_1", status="failed", exit_code=1, stdout="", stderr="", duration_seconds=0.1)

        inputs = iter(["invalid", "c"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        decision = prompter.prompt_step_failure(step=step, result=result, diagnostic="")
        assert decision == FailurePromptDecision.CONTINUE
        assert "Invalid option" in buf.getvalue()

    def test_prompt_step_failure_eof_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
        prompter = DispatcherFailurePrompter(dispatcher)

        step = StepDefinition(id="s1", run="test")
        result = StepResult(step_id="s1", status="failed", exit_code=1, stdout="", stderr="", duration_seconds=0.1)

        def raise_eof(_: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        decision = prompter.prompt_step_failure(step=step, result=result, diagnostic="")
        assert decision == FailurePromptDecision.ABORT

    def test_prompt_loop_max_iterations_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dispatcher, buf = make_dispatcher_with_buffer(force_terminal=True)
        prompter = DispatcherFailurePrompter(dispatcher, kind="workflow")

        loop = LoopStepBlock(
            id="loop_1",
            type="loop",
            max_iterations=5,
            until=["steps.s1.exit_code == 0"],
            do=[StepDefinition(id="s1", run="echo 1")],
        )

        monkeypatch.setattr("builtins.input", lambda _: "g")
        decision = prompter.prompt_loop_max_iterations(
            loop=loop,
            iteration=5,
            diagnostic="Condition not met",
            grant_count=4,
        )
        assert decision == LoopPromptDecision.GRANT
        rendered = buf.getvalue()
        assert "[loop_1] Reached max_iterations (5)" in rendered
        assert "Grant 4 additional iterations" in rendered

    def test_prompt_loop_max_iterations_eof_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
        prompter = DispatcherFailurePrompter(dispatcher)

        loop = LoopStepBlock(
            id="loop_1",
            type="loop",
            max_iterations=3,
            until=["steps.s1.exit_code == 0"],
            do=[StepDefinition(id="s1", run="echo 1")],
        )

        def raise_eof(_: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        decision = prompter.prompt_loop_max_iterations(loop=loop, iteration=3, diagnostic="")
        assert decision == LoopPromptDecision.ABORT

    def test_json_ipc_mode_emits_event_and_aborts_without_blocking(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)

        dispatcher = UiDispatcher(output_format="json")
        prompter = DispatcherFailurePrompter(dispatcher, kind="task")

        step = StepDefinition(id="s1", name="lint", run="ruff check")
        result = StepResult(step_id="s1", status="failed", exit_code=1, stdout="", stderr="err", duration_seconds=0.2)

        decision = prompter.prompt_step_failure(step=step, result=result, diagnostic="ruff syntax error")
        assert decision == FailurePromptDecision.ABORT

        lines = [line for line in stdout_buf.getvalue().splitlines() if line.strip()]
        assert len(lines) == 1
        envelope = json.loads(lines[0])
        assert envelope["event_type"] == "PromptEvent"
        payload = envelope["payload"]
        assert payload["prompt_type"] == "step_failure"
        assert payload["prompt_id"] == "s1"
        assert payload["title"] == "Step 'lint' failed (exit code 1)."
        assert payload["diagnostic"] == "ruff syntax error"
        assert len(payload["options"]) == 3
        assert payload["default"] == "abort"

    def test_non_interactive_terminal_aborts_immediately(self) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=False)
        prompter = DispatcherFailurePrompter(dispatcher)

        step = StepDefinition(id="s1", run="test")
        result = StepResult(step_id="s1", status="failed", exit_code=1, stdout="", stderr="", duration_seconds=0.1)

        decision = prompter.prompt_step_failure(step=step, result=result, diagnostic="")
        assert decision == FailurePromptDecision.ABORT


class TestPromptFormatter:
    """Tests for PromptFormatter."""

    def test_to_rich_and_json(self) -> None:
        formatter = PromptFormatter()
        event = PromptEvent(
            prompt_type="step_failure",
            prompt_id="s1",
            kind="task",
            title="Step failed",
            diagnostic="detail",
            options=[PromptOption(key="r", label="Retry", decision="retry")],
            default="abort",
        )

        rich_group = formatter.to_rich(event)
        assert rich_group is not None

        json_data = formatter.to_json_serializable(event)
        assert json_data["prompt_id"] == "s1"
        assert json_data["options"][0]["key"] == "r"
