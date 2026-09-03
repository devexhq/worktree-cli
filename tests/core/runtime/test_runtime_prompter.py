"""Unit tests for runtime CLI failure prompter."""

from __future__ import annotations

import sys

import pytest

from tests.helpers import RichOutput, make_rich_output
from worktree.core.runtime.models import FailurePromptDecision, LoopPromptDecision
from worktree.core.runtime.prompter import CliFailurePrompter
from worktree.core.step import StepDefinition, StepResult


class CliFailurePrompterTests:
    """Unit tests for CliFailurePrompter interaction and decision resolution."""

    def test_is_interactive_delegates_to_stdin_isatty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompter = CliFailurePrompter(RichOutput())

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        assert prompter.is_interactive is True

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert prompter.is_interactive is False

    @pytest.mark.parametrize(
        ("raw_input", "expected_decision"),
        [
            ("r", FailurePromptDecision.RETRY),
            ("retry", FailurePromptDecision.RETRY),
            ("c", FailurePromptDecision.CONTINUE),
            ("continue", FailurePromptDecision.CONTINUE),
            ("a", FailurePromptDecision.ABORT),
            ("abort", FailurePromptDecision.ABORT),
            ("  R  ", FailurePromptDecision.RETRY),
        ],
    )
    def test_prompt_step_failure_valid_decisions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        raw_input: str,
        expected_decision: FailurePromptDecision,
    ) -> None:
        output, buffer = make_rich_output()
        prompter = CliFailurePrompter(output, kind="task")
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

        assert decision == expected_decision
        output.print()
        rendered = buffer.getvalue()
        assert "Step 'Build Step' failed (exit code 2)." in rendered
        assert "Compilation failed on line 10" in rendered
        assert "Task paused waiting for user input." in rendered
        assert "Options:" in rendered

    def test_prompt_step_failure_workflow_kind_and_fallback_step_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        output, buffer = make_rich_output()
        prompter = CliFailurePrompter(output, kind="workflow")
        step = StepDefinition(id="step_unnamed", run="echo test")
        result = StepResult(
            step_id="step_unnamed",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.1,
        )

        monkeypatch.setattr("builtins.input", lambda _: "a")
        decision = prompter.prompt_step_failure(
            step=step,
            result=result,
            diagnostic="",
        )

        assert decision == FailurePromptDecision.ABORT
        output.print()
        rendered = buffer.getvalue()
        assert "Step 'step_unnamed' failed (exit code 1)." in rendered
        assert "Workflow paused waiting for user input." in rendered

    def test_prompt_step_failure_retries_on_invalid_input_and_eof(self, monkeypatch: pytest.MonkeyPatch) -> None:
        output, buffer = make_rich_output()
        prompter = CliFailurePrompter(output)
        step = StepDefinition(id="step_1", name="Test Step", run="pytest")
        result = StepResult(
            step_id="step_1",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.1,
        )

        inputs = iter(["invalid_choice", EOFError(), "c"])

        def _mock_input(_prompt: str) -> str:
            val = next(inputs)
            if isinstance(val, Exception):
                raise val
            return val

        monkeypatch.setattr("builtins.input", _mock_input)
        decision = prompter.prompt_step_failure(
            step=step,
            result=result,
            diagnostic="Test failure",
        )

        assert decision == FailurePromptDecision.CONTINUE
        output.print()
        rendered = buffer.getvalue()
        assert "Invalid option. Enter r, c, or a (retry/continue/abort)." in rendered

    @pytest.mark.parametrize(
        ("raw_input", "expected_decision"),
        [
            ("g", LoopPromptDecision.GRANT),
            ("grant", LoopPromptDecision.GRANT),
            ("c", LoopPromptDecision.CONTINUE),
            ("continue", LoopPromptDecision.CONTINUE),
            ("a", LoopPromptDecision.ABORT),
            ("abort", LoopPromptDecision.ABORT),
            ("  G  ", LoopPromptDecision.GRANT),
        ],
    )
    def test_prompt_loop_max_iterations_valid_decisions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        raw_input: str,
        expected_decision: LoopPromptDecision,
    ) -> None:
        from worktree.core.step import LoopStepBlock

        output, buffer = make_rich_output()
        prompter = CliFailurePrompter(output)
        loop = LoopStepBlock(
            id="retry_block",
            type="loop",
            max_iterations=5,
            until=["steps.check.exit_code == 0"],
            do=[StepDefinition(id="check", run="echo hi")],
        )

        monkeypatch.setattr("builtins.input", lambda _: raw_input)
        decision = prompter.prompt_loop_max_iterations(
            loop=loop,
            iteration=5,
            diagnostic="Loop did not converge",
            grant_count=3,
        )

        assert decision == expected_decision
        output.print()
        rendered = buffer.getvalue()
        assert "[retry_block] Reached max_iterations (5) without meeting 'until' conditions." in rendered
        assert "Loop block paused." in rendered
        assert "[g] Grant 3 additional iterations" in rendered

    def test_prompt_loop_max_iterations_retries_on_invalid_input(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from worktree.core.step import LoopStepBlock

        output, buffer = make_rich_output()
        prompter = CliFailurePrompter(output)
        loop = LoopStepBlock(
            id="retry_block",
            type="loop",
            max_iterations=3,
            until=["steps.check.exit_code == 0"],
            do=[StepDefinition(id="check", run="echo hi")],
        )

        inputs = iter(["bad_choice", EOFError(), "c"])

        def _mock_input(_prompt: str) -> str:
            val = next(inputs)
            if isinstance(val, Exception):
                raise val
            return val

        monkeypatch.setattr("builtins.input", _mock_input)
        decision = prompter.prompt_loop_max_iterations(
            loop=loop,
            iteration=3,
            diagnostic="",
        )

        assert decision == LoopPromptDecision.CONTINUE
        output.print()
        rendered = buffer.getvalue()
        assert "Invalid option. Enter g, c, or a (grant/continue/abort)." in rendered
