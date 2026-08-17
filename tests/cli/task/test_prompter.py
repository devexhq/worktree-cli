"""Unit tests for the CLI FailurePrompter adapter."""

import pytest

from worktree.cli.task.prompter import CliFailurePrompter
from worktree.common.utils import RichOutput
from worktree.core.runtime import FailurePromptDecision
from worktree.core.step import StepDefinition, StepResult, StepType


class _FakeConsole:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message="") -> None:
        self.messages.append(str(message))


def _step() -> StepDefinition:
    return StepDefinition(
        id="create-plan",
        name="create-plan",
        type=StepType.COMMAND,
        command="false",
    )


def _result() -> StepResult:
    return StepResult(
        step_id="create-plan",
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        duration_seconds=0.01,
        error_message="details",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("r", FailurePromptDecision.RETRY),
        ("retry", FailurePromptDecision.RETRY),
        ("c", FailurePromptDecision.CONTINUE),
        ("continue", FailurePromptDecision.CONTINUE),
        ("a", FailurePromptDecision.ABORT),
        ("abort", FailurePromptDecision.ABORT),
    ],
)
def test_cli_failure_prompter_accepts_short_and_long_choices(
    raw: str,
    expected: FailurePromptDecision,
) -> None:
    console = _FakeConsole()
    prompter = CliFailurePrompter(
        RichOutput(console=console),  # type: ignore[arg-type]
        kind="task",
        input_fn=lambda _p, value=raw: value,
        stdin_isatty=True,
    )
    decision = prompter.prompt_step_failure(
        step=_step(),
        result=_result(),
        diagnostic="details",
    )
    assert decision == expected


def test_cli_failure_prompter_reprompts_on_invalid_input() -> None:
    answers = iter(["x", "nope", "c"])
    console = _FakeConsole()
    prompter = CliFailurePrompter(
        RichOutput(console=console),  # type: ignore[arg-type]
        kind="task",
        input_fn=lambda _p: next(answers),
        stdin_isatty=True,
    )
    decision = prompter.prompt_step_failure(
        step=_step(),
        result=_result(),
        diagnostic="details",
    )
    assert decision == FailurePromptDecision.CONTINUE
    joined = "\n".join(console.messages)
    assert "Invalid option" in joined
    assert "Task paused waiting for user input." in joined


def test_cli_failure_prompter_workflow_copy() -> None:
    console = _FakeConsole()
    prompter = CliFailurePrompter(
        RichOutput(console=console),  # type: ignore[arg-type]
        kind="workflow",
        input_fn=lambda _p: "a",
        stdin_isatty=True,
    )
    prompter.prompt_step_failure(
        step=_step(),
        result=_result(),
        diagnostic="details",
    )
    joined = "\n".join(console.messages)
    assert "Workflow paused waiting for user input." in joined
