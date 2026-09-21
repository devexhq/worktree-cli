"""Contract tests for the shared run_steps engine: execution, failure prompts, checkpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.harness.builders import StepBuilder, WorkspaceBuilder
from worktree.common.models import FailurePolicy, OnFailureSpec
from worktree.core.db import RunStatus
from worktree.core.runtime import (
    USER_CONTINUED_MARKER,
    FailurePromptDecision,
    FailurePrompter,
    LoopPromptDecision,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunPauseStore,
    run_steps,
)
from worktree.core.sandbox import Sandbox, SandboxApplyResult, SandboxApplyStatus
from worktree.core.step.models import ConditionEvaluationResult, LoopStepBlock, StepDefinition, StepResult


class _RefusingFailurePrompter(FailurePrompter):
    """Test double refusing every FailurePrompter hook by raising; subclass and override only what a test needs."""

    def __init__(self) -> None:
        self.calls = 0

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        self.calls += 1
        raise AssertionError("prompt_step_failure should not be called")

    def prompt_loop_max_iterations(self, **kwargs: object) -> LoopPromptDecision:
        raise AssertionError("prompt_loop_max_iterations should not be called")


class _ScriptedFailurePrompter(_RefusingFailurePrompter):
    """Test double returning a scripted queue of FailurePromptDecision values."""

    def __init__(self, decisions: list[FailurePromptDecision]) -> None:
        super().__init__()
        self.decisions = list(decisions)

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        self.calls += 1
        return self.decisions.pop(0)


class _InMemoryPauseStore(RunPauseStore):
    """Test double recording every persisted checkpoint and pause-clear call."""

    def __init__(self) -> None:
        self.checkpoints: list[RunCheckpoint] = []
        self.cleared = 0

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        self.checkpoints.append(checkpoint)

    def clear_pause(self) -> None:
        self.cleared += 1


class _AssertsCheckpointSavedPrompter(_RefusingFailurePrompter):
    """Test double asserting a checkpoint was persisted before it is consulted."""

    def __init__(self, store: _InMemoryPauseStore) -> None:
        super().__init__()
        self.store = store

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        self.calls += 1
        assert self.store.checkpoints
        return FailurePromptDecision.ABORT


class _InterruptingFailurePrompter(_RefusingFailurePrompter):
    """Test double simulating a Ctrl-C during an interactive prompt."""

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        raise KeyboardInterrupt


class _NoOpRunObserver(RunObserver):
    """Test double implementing every RunObserver hook as a no-op; subclass and override only what a test needs."""

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        pass

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        pass

    def on_step_output(self, idx: int, total: int, step: StepDefinition, line: str, stream: str = "stdout") -> None:
        pass

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        pass

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        pass

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        pass

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        pass

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        pass

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        pass


class _RecordingRunObserver(_NoOpRunObserver):
    """Test double implementing RunObserver, recording every lifecycle event in call order."""

    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        self.events.append(("sandbox_ready", path, active))

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        self.events.append(("step_start", idx, total, step.id))

    def on_step_output(
        self,
        idx: int,
        total: int,
        step: StepDefinition,
        line: str,
        stream: str = "stdout",
    ) -> None:
        self.events.append(("step_output", idx, total, step.id, line, stream))

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        self.events.append(("step_done", idx, total, result.step_id))

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        self.events.append(("loop_start", loop_id, max_iterations))

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        self.events.append(("sandbox_cleanup", kept, path))


class _InterruptingStepStartObserver(_NoOpRunObserver):
    """Test double implementing RunObserver, raising KeyboardInterrupt when a step starts."""

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        raise KeyboardInterrupt


class _ExplodingRunObserver(_NoOpRunObserver):
    """Test double implementing RunObserver, raising from every lifecycle hook."""

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        raise RuntimeError("sandbox ready exploded")

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        raise RuntimeError("step start exploded")

    def on_step_output(self, idx: int, total: int, step: StepDefinition, line: str, stream: str = "stdout") -> None:
        raise RuntimeError("step output exploded")

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        raise RuntimeError("step done exploded")

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        raise RuntimeError("loop start exploded")

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        raise RuntimeError("loop turn exploded")

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        raise RuntimeError("conditions exploded")

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        raise RuntimeError("loop done exploded")

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        raise RuntimeError("cleanup exploded")


def _step_result(
    step_id: str,
    *,
    status: str,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    attempts: int = 1,
    error_message: str | None = None,
) -> StepResult:
    """Build an expected StepResult for comparison."""
    return StepResult.model_construct(
        step_id=step_id,
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.0,
        attempts=attempts,
        error_message=error_message,
        errors=[],
        warnings=[],
        fixes=[],
    )


def _assert_step_results(actual_steps: list[StepResult], expected_steps: list[StepResult]) -> None:
    assert len(actual_steps) == len(expected_steps)
    for actual_step, expected_step in zip(actual_steps, expected_steps, strict=False):
        assert actual_step.step_id == expected_step.step_id
        assert actual_step.status == expected_step.status
        assert actual_step.exit_code == expected_step.exit_code
        if expected_step.stdout:
            assert actual_step.stdout == expected_step.stdout
        if expected_step.stderr:
            assert actual_step.stderr == expected_step.stderr
        if expected_step.error_message:
            assert actual_step.error_message == expected_step.error_message
        assert actual_step.attempts == expected_step.attempts


class RunStepsExecutionTests:
    """Contract tests for run_steps' linear execution sequence and outcome shape."""

    def test_run_steps_two_sequential_steps_returns_completed_outcome_with_both_results(self, tmp_path: Path) -> None:
        context = RunContext(
            steps=[
                StepBuilder.command("echo one").with_id("s1").build(),
                StepBuilder.command("echo two").with_id("s2").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result("s1", status="completed", exit_code=0, stdout="one\n"),
                _step_result("s2", status="completed", exit_code=0, stdout="two\n"),
            ],
        )

    def test_run_steps_streams_step_output_to_observer_by_line_and_stream(self, tmp_path: Path) -> None:
        observer = _RecordingRunObserver()
        step1 = StepBuilder.command("python3 -c \"print('line 1'); print('line 2')\"").with_id("s1").build()
        step2 = StepBuilder.command("python3 -c \"import sys; sys.stderr.write('err 1\\n')\"").with_id("s2").build()
        context = RunContext(steps=[step1, step2], cwd=tmp_path, use_sandbox=False, observer=observer)

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result("s1", status="completed", exit_code=0, stdout="line 1\nline 2\n"),
                _step_result("s2", status="completed", exit_code=0, stderr="err 1\n"),
            ],
        )
        output_events = [event for event in observer.events if event[0] == "step_output"]
        assert output_events == [
            ("step_output", 1, 2, "s1", "line 1\n", "stdout"),
            ("step_output", 1, 2, "s1", "line 2\n", "stdout"),
            ("step_output", 2, 2, "s2", "err 1\n", "stderr"),
        ]

    def test_run_steps_with_sandbox_completes_and_removes_worktree_after_run(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
        context = RunContext(
            steps=[StepBuilder.command("echo sandboxed").with_id("s1").build()],
            cwd=workspace,
            use_sandbox=True,
            keep=False,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_kept is False
        _assert_step_results(
            outcome.step_results,
            [_step_result("s1", status="completed", exit_code=0, stdout="sandboxed\n")],
        )
        assert not outcome.sandbox_path.exists()

    def test_run_steps_abort_on_failure_stops_before_later_steps(self, tmp_path: Path) -> None:
        context = RunContext(
            steps=[
                StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.ABORT).build(),
                StepBuilder.command("echo should-not-run").with_id("later").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )

    def test_run_steps_continue_on_failure_marks_step_ignored_and_runs_remaining_steps(self, tmp_path: Path) -> None:
        context = RunContext(
            steps=[
                StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.CONTINUE).build(),
                StepBuilder.command("echo recovered").with_id("ok").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="ignored",
                    exit_code=0,
                    error_message="Command failed with exit code 1.",
                ),
                _step_result("ok", status="completed", exit_code=0, stdout="recovered\n"),
            ],
        )

    def test_run_steps_keep_sandbox_true_preserves_worktree_after_completed_run(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
        context = RunContext(
            steps=[StepBuilder.command("echo keep-me").with_id("s1").build()],
            cwd=workspace,
            use_sandbox=True,
            keep=True,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_kept is True
        _assert_step_results(
            outcome.step_results,
            [_step_result("s1", status="completed", exit_code=0, stdout="keep-me\n")],
        )
        assert outcome.sandbox_path.is_dir()

    def test_run_steps_observer_receives_sandbox_step_and_cleanup_callbacks_in_order(self, tmp_path: Path) -> None:
        observer = _RecordingRunObserver()
        context = RunContext(
            steps=[StepBuilder.command("echo one").with_id("s1").build()],
            cwd=tmp_path,
            use_sandbox=False,
            observer=observer,
        )

        outcome = run_steps(context)

        resolved = tmp_path.resolve()
        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == resolved
        _assert_step_results(
            outcome.step_results,
            [_step_result("s1", status="completed", exit_code=0, stdout="one\n")],
        )
        lifecycle_events = [event for event in observer.events if event[0] != "step_output"]
        assert lifecycle_events == [
            ("sandbox_ready", resolved, False),
            ("step_start", 1, 1, "s1"),
            ("step_done", 1, 1, "s1"),
            ("sandbox_cleanup", False, resolved),
        ]

    def test_run_steps_keyboard_interrupt_during_step_cancels_run(self, tmp_path: Path) -> None:
        context = RunContext(
            steps=[StepBuilder.command("echo one").with_id("s1").build()],
            cwd=tmp_path,
            use_sandbox=False,
            observer=_InterruptingStepStartObserver(),
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.CANCELLED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Execution cancelled by user."]

    def test_run_steps_empty_step_list_returns_completed_outcome_with_no_results(self, tmp_path: Path) -> None:
        context = RunContext(steps=[], cwd=tmp_path, use_sandbox=False)

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.step_results == []

    def test_run_steps_sandbox_creation_failure_without_git_repo_returns_failed_outcome(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").build()
        context = RunContext(
            steps=[StepBuilder.command("echo x").with_id("s1").build()],
            cwd=workspace,
            use_sandbox=True,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == workspace
        assert len(outcome.errors) > 0
        assert "Git sandbox creation failed" in outcome.errors[0]


class RunStepsFailurePromptTests:
    """Contract tests covering every FailurePromptDecision branch (RETRY, CONTINUE, ABORT)."""

    def test_run_steps_prompt_user_abort_decision_stops_run_and_records_error(self, tmp_path: Path) -> None:
        prompter = _ScriptedFailurePrompter([FailurePromptDecision.ABORT])
        context = RunContext(
            steps=[
                StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build(),
                StepBuilder.command("echo later").with_id("later").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )
        assert prompter.calls == 1

    def test_run_steps_prompt_user_continue_decision_marks_step_ignored_and_continues(self, tmp_path: Path) -> None:
        prompter = _ScriptedFailurePrompter([FailurePromptDecision.CONTINUE])
        context = RunContext(
            steps=[
                StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build(),
                StepBuilder.command("echo later").with_id("later").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="ignored",
                    exit_code=1,
                    error_message=f"Command failed with exit code 1. ({USER_CONTINUED_MARKER})",
                ),
                _step_result("later", status="completed", exit_code=0, stdout="later\n"),
            ],
        )
        assert prompter.calls == 1

    def test_run_steps_prompt_user_retry_decision_reexecutes_step_until_success(self, tmp_path: Path) -> None:
        prompter = _ScriptedFailurePrompter([FailurePromptDecision.RETRY])
        command = 'if [ "$WT_STEP_ATTEMPT" -eq 1 ]; then exit 1; else exit 0; fi'
        context = RunContext(
            steps=[StepBuilder.command(command).with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build()],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [_step_result("fail", status="completed", exit_code=0, attempts=2)],
        )
        assert prompter.calls == 1

    @pytest.mark.parametrize(
        ("ctx_kwargs", "prompter", "warning_substr"),
        [
            pytest.param({"no_tty": True}, _RefusingFailurePrompter(), "non-interactive", id="no_tty"),
            pytest.param({}, None, "no failure prompter", id="no_prompter"),
        ],
    )
    def test_run_steps_prompt_user_skips_prompt_and_aborts_when_non_interactive(
        self,
        tmp_path: Path,
        ctx_kwargs: dict[str, Any],
        prompter: _RefusingFailurePrompter | None,
        warning_substr: str,
    ) -> None:
        context = RunContext(
            steps=[StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build()],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
            **ctx_kwargs,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert len(outcome.errors) > 0
        assert len(outcome.warnings) > 0
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )
        assert warning_substr in outcome.warnings[0]
        if prompter is not None:
            assert prompter.calls == 0

    def test_run_steps_retry_exhausted_escalates_to_on_max_retries_prompt(self, tmp_path: Path) -> None:
        prompter = _ScriptedFailurePrompter([FailurePromptDecision.ABORT])
        context = RunContext(
            steps=[
                StepBuilder.command("exit 1")
                .with_id("fail")
                .with_on_failure(
                    OnFailureSpec(action=FailurePolicy.RETRY, max_retries=2, on_max_retries=FailurePolicy.PROMPT_USER)
                )
                .build()
            ],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    attempts=2,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )
        assert prompter.calls == 1


class RunStepsPauseAndResumeTests:
    """Contract tests for RunCheckpoint persistence and resume-from-checkpoint behavior."""

    def test_run_steps_persists_checkpoint_before_prompting_and_clears_pause_after_decision(
        self, tmp_path: Path
    ) -> None:
        store = _InMemoryPauseStore()
        prompter = _AssertsCheckpointSavedPrompter(store)
        context = RunContext(
            steps=[StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build()],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
            pause_store=store,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )
        assert len(store.checkpoints) == 1
        assert store.checkpoints[0].pending_step_id == "fail"
        assert store.checkpoints[0].next_step_index == 0
        assert store.cleared == 1

    def test_run_steps_no_tty_never_persists_checkpoint_or_clears_pause(self, tmp_path: Path) -> None:
        store = _InMemoryPauseStore()
        context = RunContext(
            steps=[StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build()],
            cwd=tmp_path,
            use_sandbox=False,
            no_tty=True,
            pause_store=store,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert len(outcome.errors) > 0
        assert len(outcome.warnings) > 0
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )
        assert store.checkpoints == []
        assert store.cleared == 0

    def test_run_steps_keyboard_interrupt_after_checkpoint_returns_paused_and_keeps_sandbox(
        self, tmp_path: Path
    ) -> None:
        store = _InMemoryPauseStore()
        context = RunContext(
            steps=[StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build()],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=_InterruptingFailurePrompter(),
            pause_store=store,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.PAUSED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.sandbox_kept is True
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        assert store.checkpoints
        assert store.cleared == 0

    def test_run_steps_resume_from_checkpoint_reprompts_pending_step_and_skips_completed_steps(
        self, tmp_path: Path
    ) -> None:
        prior_ok = StepResult(
            step_id="ok",
            status="completed",
            exit_code=0,
            stdout="",
            stderr="",
            duration_seconds=0.01,
            attempts=1,
            error_message=None,
            errors=[],
            warnings=[],
            fixes=[],
        )
        prior_fail = StepResult(
            step_id="fail",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.01,
            attempts=1,
            error_message="Command failed with exit code 1.",
            errors=[],
            warnings=[],
            fixes=[],
        )
        checkpoint = RunCheckpoint(
            next_step_index=1,
            step_results=[prior_ok],
            sandbox_path=str(tmp_path),
            use_sandbox=False,
            keep=False,
            pending_step_id="fail",
            diagnostic="Step 'fail' failed: Command failed with exit code 1.",
            pending_result=prior_fail,
        )
        prompter = _ScriptedFailurePrompter([FailurePromptDecision.CONTINUE])
        context = RunContext(
            steps=[
                StepBuilder.command("echo ok").with_id("ok").build(),
                StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.PROMPT_USER).build(),
                StepBuilder.command("echo later").with_id("later").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=prompter,
            resume_from=checkpoint,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                prior_ok,
                prior_fail.model_copy(
                    update={
                        "status": "ignored",
                        "error_message": f"Command failed with exit code 1. ({USER_CONTINUED_MARKER})",
                    }
                ),
                _step_result("later", status="completed", exit_code=0, stdout="later\n"),
            ],
        )
        assert prompter.calls == 1


class RunStepsRobustnessTests:
    """Contract tests for observer isolation, serial execution, loop dispatch, and cleanup failures."""

    def test_run_steps_observer_exceptions_do_not_abort_run(self, tmp_path: Path) -> None:
        context = RunContext(
            steps=[
                StepBuilder.command("echo one").with_id("s1").build(),
                StepBuilder.command("echo two").with_id("s2").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
            observer=_ExplodingRunObserver(),
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result("s1", status="completed", exit_code=0, stdout="one\n"),
                _step_result("s2", status="completed", exit_code=0, stdout="two\n"),
            ],
        )

    def test_run_steps_sandbox_cleanup_failure_after_step_failure_still_reports_failed_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()

        def _exploding_cleanup(self: Sandbox, session: object, **kwargs: object) -> list[str]:
            raise RuntimeError("Cleanup filesystem removal failed")

        monkeypatch.setattr(Sandbox, "cleanup", _exploding_cleanup)
        context = RunContext(
            steps=[StepBuilder.command("exit 1").with_id("fail").with_on_failure(FailurePolicy.ABORT).build()],
            cwd=workspace,
            use_sandbox=True,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_kept is False
        assert outcome.errors == ["Step 'fail' failed: Command failed with exit code 1."]
        _assert_step_results(
            outcome.step_results,
            [
                _step_result(
                    "fail",
                    status="failed",
                    exit_code=1,
                    error_message="Command failed with exit code 1.",
                ),
            ],
        )

    def test_run_steps_executes_steps_strictly_serially_never_concurrently(self, tmp_path: Path) -> None:
        tracker = tmp_path / "tracker.log"

        def _command(step_id: str) -> str:
            return f'echo "{step_id} start" >> {tracker}; sleep 0.05; echo "{step_id} end" >> {tracker}'

        context = RunContext(
            steps=[
                StepBuilder.command(_command("step1")).with_id("step1").build(),
                StepBuilder.command(_command("step2")).with_id("step2").build(),
                StepBuilder.command(_command("step3")).with_id("step3").build(),
            ],
            cwd=tmp_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result("step1", status="completed", exit_code=0),
                _step_result("step2", status="completed", exit_code=0),
                _step_result("step3", status="completed", exit_code=0),
            ],
        )
        assert tracker.read_text().splitlines() == [
            "step1 start",
            "step1 end",
            "step2 start",
            "step2 end",
            "step3 start",
            "step3 end",
        ]

    def test_run_steps_loop_prompter_keyboard_interrupt_cancels_run(self, tmp_path: Path) -> None:
        loop = LoopStepBlock(
            id="interrupt-loop",
            type="loop",
            max_iterations=3,
            until=["steps.check.exit_code == 0"],
            do=[StepBuilder.command("exit 1").with_id("check").with_on_failure(FailurePolicy.PROMPT_USER).build()],
        )
        context = RunContext(
            steps=[loop],
            cwd=tmp_path,
            use_sandbox=False,
            failure_prompter=_InterruptingFailurePrompter(),
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.CANCELLED
        assert outcome.sandbox_path == tmp_path.resolve()
        assert outcome.errors == ["Execution cancelled by user."]

    def test_run_steps_sequential_loop_blocks_interleave_with_plain_steps_in_order(self, tmp_path: Path) -> None:
        observer = _RecordingRunObserver()
        step1 = StepBuilder.command("echo ready").with_id("setup").with_name("Setup Step").build()
        loop1 = LoopStepBlock(
            id="loop-one",
            type="loop",
            max_iterations=3,
            until=["steps.poll1.exit_code == 0"],
            do=[StepBuilder.command("echo p1").with_id("poll1").with_name("Poll One").build()],
        )
        loop2 = LoopStepBlock(
            id="loop-two",
            type="loop",
            max_iterations=3,
            until=["steps.poll2.exit_code == 0"],
            do=[StepBuilder.command("echo p2").with_id("poll2").with_name("Poll Two").build()],
        )
        step2 = StepBuilder.command("echo done").with_id("teardown").with_name("Teardown Step").build()
        context = RunContext(steps=[step1, loop1, loop2, step2], cwd=tmp_path, use_sandbox=False, observer=observer)

        outcome = run_steps(context)

        assert outcome.status == RunStatus.COMPLETED
        assert outcome.sandbox_path == tmp_path.resolve()
        _assert_step_results(
            outcome.step_results,
            [
                _step_result("setup", status="completed", exit_code=0, stdout="ready\n"),
                _step_result("poll1", status="completed", exit_code=0, stdout="p1\n"),
                _step_result("poll2", status="completed", exit_code=0, stdout="p2\n"),
                _step_result("teardown", status="completed", exit_code=0, stdout="done\n"),
            ],
        )
        loop_starts = [event for event in observer.events if event[0] == "loop_start"]
        assert loop_starts == [("loop_start", "loop-one", 3), ("loop_start", "loop-two", 3)]

    def test_run_steps_auto_apply_conflict_marks_run_failed_and_keeps_sandbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
        fake_apply_result = SandboxApplyResult(
            sandbox_id="test-session",
            status=SandboxApplyStatus.CONFLICT,
            errors=["Patch merge conflict in sandbox apply"],
            warnings=["Patch hunk rejected"],
        )
        monkeypatch.setattr(Sandbox, "apply", lambda *args, **kwargs: fake_apply_result)
        context = RunContext(
            steps=[StepBuilder.command("echo change").with_id("s1").build()],
            cwd=workspace,
            use_sandbox=True,
            auto_apply=True,
        )

        outcome = run_steps(context)

        assert outcome.status == RunStatus.FAILED
        assert outcome.sandbox_kept is True
        assert outcome.errors == ["Patch merge conflict in sandbox apply"]
        assert outcome.warnings == ["Patch hunk rejected"]
        _assert_step_results(
            outcome.step_results,
            [_step_result("s1", status="completed", exit_code=0, stdout="change\n")],
        )
