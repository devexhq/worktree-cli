"""Unit/integration tests for the shared run_steps engine."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import (
    FileSystem,
    GitFileSystem,
    make_cmd_step,
    make_failed_result,
    make_ok_result,
)
from worktree.core.db import RunStatus
from worktree.core.runtime import (
    USER_CONTINUED_MARKER,
    FailurePromptDecision,
    FailurePrompter,
    RunCheckpoint,
    RunContext,
    RunObserver,
    run_steps,
)
from worktree.core.sandbox import (
    Sandbox,
    SandboxApplyResult,
    SandboxApplyStatus,
)
from worktree.core.step import (
    FailurePolicy,
    FailureSpec,
    LoopStepBlock,
    StepDefinition,
    StepResult,
)


def make_run_context(
    *,
    fs: FileSystem,
    steps: Sequence[StepDefinition | LoopStepBlock] | None = None,
    **kwargs: Any,
) -> RunContext:
    """Build a RunContext with test-friendly defaults; override via kwargs."""
    defaults: dict[str, Any] = {
        "steps": steps if steps is not None else [make_cmd_step(step_id="s1")],
        "cwd": fs.base_path,
        "use_sandbox": False,
    }
    defaults.update(kwargs)
    return RunContext(**defaults)


def patch_execute(
    monkeypatch: pytest.MonkeyPatch,
    behavior: Any = None,
) -> list[str]:
    """Patch engine.StepExecution and return the list of executed step ids.

    ``behavior`` may be:
    - a StepResult (returned for every call, step_id rewritten)
    - an exception instance/class to raise
    - a callable(step) -> StepResult | BaseException
    - a dict keyed by step id: result, sequence of results (consumed in order),
      or callable(step)
    - None: succeed with ``make_ok_result(step_id=step.id)``
    """
    calls: list[str] = []
    queues: dict[str, list[StepResult]] = {}
    if isinstance(behavior, dict):
        for step_id, value in behavior.items():
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, StepResult)):
                scripted = [item for item in value if isinstance(item, StepResult)]
                if len(scripted) != len(list(value)):
                    raise AssertionError(f"scripted results for {step_id!r} must all be StepResult instances")
                queues[str(step_id)] = scripted

    class FakeStepExecution:
        def __init__(
            self,
            metadata: Any,
            sandbox_path: Path | None = None,
            context: dict[str, Any] | None = None,
            on_output: Any = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            from worktree.core.step.models import StepExecutionContext

            if isinstance(metadata, StepExecutionContext):
                self.step = metadata.step
                self.sandbox_path = metadata.sandbox_path
                self.context = metadata.context
                self.on_output = metadata.on_output
            else:
                self.step = metadata
                self.sandbox_path = sandbox_path
                self.context = context
                self.on_output = on_output
            self.extra_kwargs = kwargs

        def run(self) -> StepResult:
            calls.append(self.step.id)
            resolved = _resolve_execute_behavior(self.step, behavior, queues)
            if isinstance(resolved, type) and issubclass(resolved, BaseException):
                raise resolved()
            if isinstance(resolved, BaseException):
                raise resolved
            return resolved

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "StepExecution", FakeStepExecution)
    return calls


def _resolve_execute_behavior(
    step: StepDefinition,
    behavior: Any,
    queues: dict[str, list[StepResult]],
) -> StepResult | BaseException | type[BaseException]:
    if behavior is None:
        return make_ok_result(step_id=step.id)
    if isinstance(behavior, StepResult):
        return behavior.model_copy(update={"step_id": step.id})
    if isinstance(behavior, type) and issubclass(behavior, BaseException):
        return behavior
    if isinstance(behavior, BaseException):
        return behavior
    if callable(behavior) and not isinstance(behavior, dict):
        outcome = behavior(step)
        if isinstance(outcome, (StepResult, BaseException)) or (
            isinstance(outcome, type) and issubclass(outcome, BaseException)
        ):
            return outcome
        raise AssertionError(f"callable execute behavior returned {outcome!r}")
    if not isinstance(behavior, dict):
        raise AssertionError(f"unsupported execute behavior: {behavior!r}")
    if step.id not in behavior:
        return make_ok_result(step_id=step.id)
    value = behavior[step.id]
    if step.id in queues:
        queue = queues[step.id]
        if not queue:
            raise AssertionError(f"no remaining scripted results for step {step.id!r}")
        return queue.pop(0)
    if isinstance(value, StepResult):
        return value.model_copy(update={"step_id": step.id})
    if callable(value):
        outcome = value(step)
        if isinstance(outcome, StepResult):
            return outcome
        raise AssertionError(f"callable execute behavior for {step.id!r} returned {outcome!r}")
    raise AssertionError(f"unsupported execute behavior for {step.id!r}: {value!r}")


class _ScriptedPrompter:
    def __init__(self, decisions: list[FailurePromptDecision]) -> None:
        self.decisions = list(decisions)
        self.calls = 0

    def prompt_step_failure(
        self,
        *,
        step: StepDefinition,
        result: StepResult,
        diagnostic: str,
    ) -> FailurePromptDecision:
        self.calls += 1
        if not self.decisions:
            raise AssertionError("prompter called with no remaining decisions")
        return self.decisions.pop(0)


class _BoomPrompter:
    """Prompter that must never be invoked."""

    def __init__(self) -> None:
        self.calls = 0

    def prompt_step_failure(self, **kwargs: Any) -> FailurePromptDecision:
        self.calls += 1
        raise AssertionError("should not prompt")


class _MemoryPauseStore:
    def __init__(self) -> None:
        self.checkpoints: list[RunCheckpoint] = []
        self.cleared = 0

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        self.checkpoints.append(checkpoint)

    def clear_pause(self) -> None:
        self.cleared += 1


class _AssertPausedPrompter:
    def __init__(self, store: _MemoryPauseStore) -> None:
        self.store = store
        self.calls = 0

    def prompt_step_failure(self, **kwargs: Any) -> FailurePromptDecision:
        self.calls += 1
        assert self.store.checkpoints
        return FailurePromptDecision.ABORT


class _InterruptPrompter:
    def prompt_step_failure(self, **kwargs: Any) -> FailurePromptDecision:
        raise KeyboardInterrupt


class RuntimeEngineExecutionTests:
    """Unit tests for run_steps execution flow and basic step runner operations."""

    def test_run_steps_success_no_sandbox(self, fs: FileSystem) -> None:
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="s1", command="echo one"),
                    make_cmd_step(step_id="s2", command="echo two"),
                ],
            )
        )

        assert outcome.ok is True
        assert len(outcome.step_results) == 2
        assert all(result.ok for result in outcome.step_results)
        assert outcome.sandbox_path == fs.base_path.resolve()
        assert outcome.sandbox_kept is False

    def test_run_steps_streams_output_to_observer(self, fs: FileSystem) -> None:
        observer = MagicMock(spec=RunObserver)
        step1 = make_cmd_step(
            step_id="s1",
            command="python3 -c \"print('line 1'); print('line 2')\"",
        )
        step2 = make_cmd_step(
            step_id="s2",
            command="python3 -c \"import sys; sys.stderr.write('err 1\\n')\"",
        )
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[step1, step2],
                observer=observer,
            )
        )

        assert outcome.ok is True
        assert len(outcome.step_results) == 2

        observer.on_step_output.assert_any_call(1, 2, step1, "line 1\n", stream="stdout")
        observer.on_step_output.assert_any_call(1, 2, step1, "line 2\n", stream="stdout")
        observer.on_step_output.assert_any_call(2, 2, step2, "err 1\n", stream="stderr")

    def test_run_steps_success_with_sandbox(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        outcome = run_steps(
            make_run_context(
                fs=git_fs,
                steps=[make_cmd_step(step_id="s1", command="echo sandboxed")],
                use_sandbox=True,
                keep=False,
            )
        )

        assert outcome.ok is True
        assert outcome.step_results[0].ok
        assert outcome.sandbox_kept is False
        assert not outcome.sandbox_path.exists()

    def test_run_steps_abort_on_failure(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = patch_execute(
            monkeypatch,
            {
                "fail": make_failed_result(),
                "later": make_ok_result(),
            },
        )
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="fail", command="exit 1", on_failure="abort"),
                    make_cmd_step(step_id="later", command="echo should-not-run"),
                ],
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert calls == ["fail"]
        assert len(outcome.step_results) == 1
        assert outcome.errors == ["Step 'fail' failed: boom"]

    def test_run_steps_continue_on_failure(self, fs: FileSystem) -> None:
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="fail", command="exit 1", on_failure="continue"),
                    make_cmd_step(step_id="ok", command="echo recovered"),
                ],
            )
        )

        assert outcome.ok is True
        assert [r.status for r in outcome.step_results] == ["ignored", "completed"]

    def test_run_steps_keep_sandbox(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        outcome = run_steps(
            make_run_context(
                fs=git_fs,
                steps=[make_cmd_step(step_id="s1", command="echo keep-me")],
                use_sandbox=True,
                keep=True,
            )
        )

        assert outcome.ok is True
        assert outcome.sandbox_kept is True
        assert outcome.sandbox_path.is_dir()

    def test_run_steps_observer_callbacks(self, fs: FileSystem) -> None:
        observer = MagicMock()
        outcome = run_steps(make_run_context(fs=fs, observer=observer))

        assert outcome.ok is True
        path = fs.base_path.resolve()
        observer.on_sandbox_ready.assert_called_once_with(path, False)
        observer.on_step_start.assert_called_once()
        start_args = observer.on_step_start.call_args.args
        assert start_args[:2] == (1, 1)
        assert start_args[2].id == "s1"
        observer.on_step_done.assert_called_once()
        done_args = observer.on_step_done.call_args.args
        assert done_args[:2] == (1, 1)
        assert isinstance(done_args[2], StepResult)
        observer.on_sandbox_cleanup.assert_called_once_with(False, path)

    def test_run_steps_keyboard_interrupt(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_execute(monkeypatch, KeyboardInterrupt)
        outcome = run_steps(make_run_context(fs=fs))

        assert outcome.status == RunStatus.CANCELLED
        assert outcome.errors == ["Execution cancelled by user."]
        assert outcome.step_results == []

    def test_run_steps_empty_steps(self, fs: FileSystem) -> None:
        outcome = run_steps(make_run_context(fs=fs, steps=[]))

        assert outcome.ok is True
        assert outcome.step_results == []

    def test_run_steps_sandbox_create_failure(self, fs: FileSystem) -> None:
        # No worktree init / config → sandbox create fails classified.
        outcome = run_steps(make_run_context(fs=fs, use_sandbox=True))

        assert outcome.status == RunStatus.FAILED
        assert outcome.step_results == []
        assert outcome.errors
        assert "Git sandbox creation failed" in outcome.errors[0]


class RuntimeEngineFailurePromptTests:
    """Unit tests for failure prompt handling during step execution."""

    def test_run_steps_prompt_user_abort(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])
        calls = patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="fail", on_failure="prompt_user"),
                    make_cmd_step(step_id="later"),
                ],
                failure_prompter=prompter,
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert calls == ["fail"]
        assert prompter.calls == 1
        assert outcome.errors == ["Step 'fail' failed: boom"]

    def test_run_steps_prompt_user_continue(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])
        patch_execute(
            monkeypatch,
            {
                "fail": make_failed_result(),
                "later": make_ok_result(),
            },
        )
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="fail", on_failure="prompt_user"),
                    make_cmd_step(step_id="later"),
                ],
                failure_prompter=prompter,
            )
        )

        assert outcome.ok is True
        assert outcome.step_results[0].status == "ignored"
        assert USER_CONTINUED_MARKER in (outcome.step_results[0].error_message or "")
        assert outcome.step_results[1].status == "completed"

    def test_run_steps_prompt_user_retry_then_success(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompter = _ScriptedPrompter([FailurePromptDecision.RETRY])
        calls = patch_execute(
            monkeypatch,
            {"fail": [make_failed_result(), make_ok_result()]},
        )
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[make_cmd_step(step_id="fail", on_failure="prompt_user")],
                failure_prompter=prompter,
            )
        )

        assert outcome.ok is True
        assert calls == ["fail", "fail"]
        assert prompter.calls == 1
        assert outcome.step_results[0].status == "completed"

    @pytest.mark.parametrize(
        ("ctx_kwargs", "prompter", "warning_substr"),
        [
            pytest.param(
                {"no_tty": True},
                _BoomPrompter(),
                "non-interactive",
                id="non-interactive",
            ),
            pytest.param(
                {},
                None,
                "no failure prompter",
                id="no-prompter",
            ),
        ],
    )
    def test_run_steps_prompt_user_skips_prompt_and_aborts(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        ctx_kwargs: dict[str, Any],
        prompter: _BoomPrompter | None,
        warning_substr: str,
    ) -> None:
        patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[make_cmd_step(step_id="fail", on_failure="prompt_user")],
                failure_prompter=prompter,
                **ctx_kwargs,
            )
        )

        assert outcome.status == RunStatus.FAILED
        if prompter is not None:
            assert prompter.calls == 0
        assert any(warning_substr in w for w in outcome.warnings)

    def test_run_steps_retry_exhausted_uses_on_max_retries_prompt(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])
        patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(
                        step_id="fail",
                        command="exit 1",
                        on_failure=FailureSpec(
                            action=FailurePolicy.RETRY,
                            max_retries=2,
                            on_max_retries=FailurePolicy.PROMPT_USER,
                        ),
                    )
                ],
                failure_prompter=prompter,
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert prompter.calls == 1


class RuntimeEnginePauseAndResumeTests:
    """Unit tests for checkpoint persistence, pause lifecycle, and resumption in run_steps."""

    def test_run_steps_persists_checkpoint_before_prompt(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = _MemoryPauseStore()
        prompter = _AssertPausedPrompter(store)
        patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[make_cmd_step(step_id="fail", on_failure="prompt_user")],
                failure_prompter=prompter,
                pause_store=store,
            )
        )

        assert prompter.calls == 1
        assert len(store.checkpoints) == 1
        assert store.checkpoints[0].pending_step_id == "fail"
        assert store.checkpoints[0].next_step_index == 0
        assert store.cleared == 1
        assert outcome.status == RunStatus.FAILED

    def test_run_steps_no_tty_never_pauses(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = _MemoryPauseStore()
        patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[make_cmd_step(step_id="fail", on_failure="prompt_user")],
                no_tty=True,
                pause_store=store,
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert store.checkpoints == []
        assert store.cleared == 0

    def test_run_steps_keyboard_interrupt_after_pause_keeps_paused(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = _MemoryPauseStore()
        patch_execute(monkeypatch, make_failed_result())
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[make_cmd_step(step_id="fail", on_failure="prompt_user")],
                failure_prompter=_InterruptPrompter(),
                pause_store=store,
            )
        )

        assert outcome.status == RunStatus.PAUSED
        assert store.checkpoints
        assert store.cleared == 0
        assert outcome.sandbox_kept is True

    def test_run_steps_resume_reprompts_and_skips_completed(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])
        calls = patch_execute(monkeypatch, {"later": make_ok_result()})
        checkpoint = RunCheckpoint(
            next_step_index=1,
            step_results=[make_ok_result(step_id="ok")],
            sandbox_path=str(fs.base_path),
            use_sandbox=False,
            keep=False,
            pending_step_id="fail",
            diagnostic="Step 'fail' failed: boom",
            pending_result=make_failed_result(step_id="fail"),
        )
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="ok"),
                    make_cmd_step(step_id="fail", on_failure="prompt_user"),
                    make_cmd_step(step_id="later"),
                ],
                failure_prompter=prompter,
                resume_from=checkpoint,
            )
        )

        assert outcome.ok is True
        assert calls == ["later"]
        assert prompter.calls == 1
        assert [result.step_id for result in outcome.step_results] == ["ok", "fail", "later"]
        assert outcome.step_results[1].status == "ignored"


class RuntimeEngineConcurrencyAndRobustnessTests:
    """Tests for observer error isolation, concurrency constraints, loop dispatch, and cleanup failure."""

    def test_observer_exceptions_do_not_abort_run_steps(self, fs: FileSystem) -> None:
        observer = MagicMock(spec=RunObserver)
        observer.on_sandbox_ready.side_effect = RuntimeError("observer sandbox ready exploded")
        observer.on_step_start.side_effect = RuntimeError("observer step start exploded")
        observer.on_step_output.side_effect = RuntimeError("observer step output exploded")
        observer.on_step_done.side_effect = RuntimeError("observer step done exploded")
        observer.on_sandbox_cleanup.side_effect = RuntimeError("observer cleanup exploded")

        step1 = make_cmd_step(step_id="s1", command="echo one")
        step2 = make_cmd_step(step_id="s2", command="echo two")
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[step1, step2],
                observer=observer,
            )
        )

        assert outcome.ok is True
        assert len(outcome.step_results) == 2
        assert all(r.ok for r in outcome.step_results)

    def test_sandbox_cleanup_failure_after_step_failure(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()
        failing_step = make_cmd_step(step_id="fail", command="exit 1", on_failure=FailurePolicy.ABORT)

        def _exploding_cleanup(self: object, session: object) -> list[str]:
            raise RuntimeError("Cleanup filesystem removal failed")

        monkeypatch.setattr(Sandbox, "cleanup", _exploding_cleanup)

        outcome = run_steps(
            make_run_context(
                fs=git_fs,
                steps=[failing_step],
                use_sandbox=True,
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert len(outcome.step_results) == 1
        assert outcome.step_results[0].step_id == "fail"
        assert outcome.step_results[0].ok is False
        assert any("Step 'fail' failed" in err for err in outcome.errors)
        assert outcome.sandbox_kept is False

    def test_steps_execute_serially_against_sandbox(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that step execution within run_steps is strictly serial, not concurrent.

        The runtime engine is deliberately single-threaded and strictly serial:
        concurrent step execution against a shared sandbox is prohibited because
        concurrent operations on a single git working tree corrupt index state (.git/index.lock)
        and break sequential step dependency invariants.
        """
        active_concurrency = 0
        max_concurrency = 0

        def _timed_execute(step: StepDefinition) -> StepResult:
            nonlocal active_concurrency, max_concurrency
            active_concurrency += 1
            if active_concurrency > max_concurrency:
                max_concurrency = active_concurrency
            active_concurrency -= 1
            return make_ok_result(step_id=step.id)

        patch_execute(monkeypatch, _timed_execute)

        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[
                    make_cmd_step(step_id="step1"),
                    make_cmd_step(step_id="step2"),
                    make_cmd_step(step_id="step3"),
                ],
            )
        )

        assert outcome.ok is True
        assert max_concurrency == 1
        assert active_concurrency == 0
        assert len(outcome.step_results) == 3

    def test_run_steps_loop_prompter_keyboard_interrupt_cancels_run(
        self,
        fs: FileSystem,
    ) -> None:
        prompter = MagicMock(spec=FailurePrompter)
        prompter.prompt_step_failure.side_effect = KeyboardInterrupt

        loop = LoopStepBlock(
            id="interrupt-loop",
            type="loop",
            max_iterations=3,
            until=["steps.check.exit_code == 0"],
            do=[make_cmd_step(step_id="check", command="exit 1", on_failure="prompt_user")],
        )

        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[loop],
                failure_prompter=prompter,
            )
        )

        assert outcome.status == RunStatus.CANCELLED
        assert any("Execution cancelled by user." in err for err in outcome.errors)

    def test_run_steps_with_sequential_loop_blocks(
        self,
        fs: FileSystem,
    ) -> None:
        step1 = make_cmd_step(step_id="setup", name="Setup Step", command="echo ready")
        loop1 = LoopStepBlock(
            id="loop-one",
            type="loop",
            max_iterations=3,
            until=["steps.poll1.exit_code == 0"],
            do=[make_cmd_step(step_id="poll1", name="Poll One", command="echo p1")],
        )
        loop2 = LoopStepBlock(
            id="loop-two",
            type="loop",
            max_iterations=3,
            until=["steps.poll2.exit_code == 0"],
            do=[make_cmd_step(step_id="poll2", name="Poll Two", command="echo p2")],
        )
        step2 = make_cmd_step(step_id="teardown", name="Teardown Step", command="echo done")

        observer = MagicMock(spec=RunObserver)
        outcome = run_steps(
            make_run_context(
                fs=fs,
                steps=[step1, loop1, loop2, step2],
                observer=observer,
            )
        )

        assert outcome.ok is True
        step_ids = [r.step_id for r in outcome.step_results]
        assert step_ids == ["setup", "poll1", "poll2", "teardown"]
        observer.on_loop_start.assert_any_call("loop-one", 3)
        observer.on_loop_start.assert_any_call("loop-two", 3)

    def test_run_steps_auto_apply_failure_marks_run_failed(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()

        fake_result = SandboxApplyResult(
            sandbox_id="test-session",
            status=SandboxApplyStatus.CONFLICT,
            errors=["Patch merge conflict in sandbox apply"],
            warnings=["Patch hunk rejected"],
        )

        monkeypatch.setattr(Sandbox, "apply", lambda *args, **kwargs: fake_result)

        step = make_cmd_step(step_id="s1", command="echo change")
        outcome = run_steps(
            make_run_context(
                fs=git_fs,
                steps=[step],
                use_sandbox=True,
                auto_apply=True,
            )
        )

        assert outcome.status == RunStatus.FAILED
        assert any("Patch merge conflict" in err for err in outcome.errors)
        assert any("Patch hunk rejected" in warn for warn in outcome.warnings)
        assert outcome.sandbox_kept is True
