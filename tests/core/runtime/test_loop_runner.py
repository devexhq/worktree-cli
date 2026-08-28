"""Unit tests for LoopBlockRunner execution, failure policies, and until evaluation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from worktree.core.runtime.loop_runner import LoopBlockRunner
from worktree.core.runtime.models import (
    LoopPromptDecision,
    RunObserver,
    StepLoopState,
)
from worktree.core.step.models import (
    FailurePolicy,
    FailureSpec,
    LoopStepBlock,
    StepDefinition,
    StepType,
)


def _make_step(
    step_id: str,
    *,
    command: str = "echo ok",
    on_failure: FailurePolicy = FailurePolicy.ABORT,
) -> StepDefinition:
    return StepDefinition(
        id=step_id,
        type=StepType.COMMAND,
        command=command,
        on_failure=FailureSpec(action=on_failure),
    )


class TestLoopBlockRunner:
    """Tests for LoopBlockRunner turn execution and conditions."""

    def test_single_turn_success(self, tmp_path: Path) -> None:
        loop = LoopStepBlock(
            id="retry-loop",
            type="loop",
            max_iterations=3,
            until=["steps.check.exit_code == 0"],
            do=[_make_step("check", command="echo success")],
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, result, error = runner.run(state)

        assert action == "continue"
        assert result is None
        assert error is None
        assert len(state.step_results) == 1
        assert state.step_results[0].step_id == "check"
        assert state.step_results[0].exit_code == 0

    def test_multi_turn_convergence_with_iteration_index(self, tmp_path: Path) -> None:
        # Step writes turn to file and succeeds on turn 2
        cmd = "if [ $WT_ITERATION_INDEX -eq 2 ]; then exit 0; else exit 1; fi"
        loop = LoopStepBlock(
            id="converge-loop",
            type="loop",
            max_iterations=3,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command=cmd, on_failure=FailurePolicy.CONTINUE)],
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, _, _ = runner.run(state)

        assert action == "continue"
        assert len(state.step_results) == 2
        assert state.step_results[0].exit_code == 1
        assert state.step_results[1].exit_code == 0

    def test_sub_step_failure_pass_through(self, tmp_path: Path) -> None:
        # Sub-step fails but on_failure: continue allows until expression to inspect it
        loop = LoopStepBlock(
            id="pass-through-loop",
            type="loop",
            max_iterations=2,
            until=["steps.failing_step.exit_code == 1"],
            do=[_make_step("failing_step", command="exit 1", on_failure=FailurePolicy.CONTINUE)],
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, _, _ = runner.run(state)

        assert action == "continue"
        assert len(state.step_results) == 1
        assert state.step_results[0].exit_code == 1

    def test_sub_step_abort_stops_loop(self, tmp_path: Path) -> None:
        loop = LoopStepBlock(
            id="abort-loop",
            type="loop",
            max_iterations=3,
            until=["steps.check.exit_code == 0"],
            do=[_make_step("fatal", command="exit 1", on_failure=FailurePolicy.ABORT)],
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, _, error = runner.run(state)

        assert action == "abort"
        assert error is not None
        assert "Step 'fatal' failed" in error

    def test_max_iterations_policy_abort(self, tmp_path: Path) -> None:
        loop = LoopStepBlock(
            id="ceiling-abort-loop",
            type="loop",
            max_iterations=2,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command="exit 1", on_failure=FailurePolicy.CONTINUE)],
            on_max_iterations=FailurePolicy.ABORT,
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, _, error = runner.run(state)

        assert action == "abort"
        assert error is not None
        assert "reached max_iterations (2)" in error
        assert len(state.step_results) == 2

    def test_max_iterations_policy_continue(self, tmp_path: Path) -> None:
        loop = LoopStepBlock(
            id="ceiling-continue-loop",
            type="loop",
            max_iterations=2,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command="exit 1", on_failure=FailurePolicy.CONTINUE)],
            on_max_iterations=FailurePolicy.CONTINUE,
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path)

        action, _, _ = runner.run(state)

        assert action == "continue"
        assert len(state.warnings) == 1
        assert "reached max_iterations (2)" in state.warnings[0]
        assert len(state.step_results) == 2

    def test_max_iterations_prompt_grant(self, tmp_path: Path) -> None:
        prompter = MagicMock()
        prompter.prompt_loop_max_iterations.return_value = LoopPromptDecision.GRANT

        cmd = "if [ $WT_ITERATION_INDEX -eq 2 ]; then exit 0; else exit 1; fi"
        loop = LoopStepBlock(
            id="grant-loop",
            type="loop",
            max_iterations=1,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command=cmd, on_failure=FailurePolicy.CONTINUE)],
            on_max_iterations=FailurePolicy.PROMPT_USER,
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path, failure_prompter=prompter)

        action, _, _ = runner.run(state)

        assert action == "continue"
        assert prompter.prompt_loop_max_iterations.call_count == 1
        assert len(state.step_results) == 2

    def test_max_iterations_prompt_continue(self, tmp_path: Path) -> None:
        prompter = MagicMock()
        prompter.prompt_loop_max_iterations.return_value = LoopPromptDecision.CONTINUE

        loop = LoopStepBlock(
            id="prompt-continue-loop",
            type="loop",
            max_iterations=1,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command="exit 1", on_failure=FailurePolicy.CONTINUE)],
            on_max_iterations=FailurePolicy.PROMPT_USER,
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path, failure_prompter=prompter)

        action, _, _ = runner.run(state)

        assert action == "continue"
        assert len(state.warnings) == 1

    def test_max_iterations_prompt_abort(self, tmp_path: Path) -> None:
        prompter = MagicMock()
        prompter.prompt_loop_max_iterations.return_value = LoopPromptDecision.ABORT

        loop = LoopStepBlock(
            id="prompt-abort-loop",
            type="loop",
            max_iterations=1,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command="exit 1", on_failure=FailurePolicy.CONTINUE)],
            on_max_iterations=FailurePolicy.PROMPT_USER,
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path, failure_prompter=prompter)

        action, _, error = runner.run(state)

        assert action == "abort"
        assert error is not None
        assert "aborted by user" in error

    def test_observer_lifecycle_events(self, tmp_path: Path) -> None:
        observer = MagicMock(spec=RunObserver)
        loop = LoopStepBlock(
            id="observed-loop",
            type="loop",
            max_iterations=2,
            until=["steps.poll.exit_code == 0"],
            do=[_make_step("poll", command="echo hello")],
        )
        state = StepLoopState(target_dir=tmp_path, session=None)
        runner = LoopBlockRunner(loop, sandbox_path=tmp_path, observer=observer)

        runner.run(state)

        observer.on_loop_start.assert_called_once_with("observed-loop", 2)
        observer.on_loop_turn_start.assert_called_once_with("observed-loop", 1, 2)
        assert observer.on_loop_conditions_evaluated.call_count == 1
        observer.on_loop_done.assert_called_once_with("observed-loop", "completed", 1)
