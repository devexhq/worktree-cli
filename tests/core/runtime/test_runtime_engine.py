"""Unit/integration tests for the shared run_steps engine."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import FileSystem, GitFileSystem
from worktree.core.db import RunStatus
from worktree.core.runtime import (
    USER_CONTINUED_MARKER,
    FailurePromptDecision,
    RunCheckpoint,
    RunContext,
    run_steps,
)
from worktree.core.step import FailurePolicy, FailureSpec, StepDefinition, StepResult, StepType


def _cmd_step(
    step_id: str,
    command: str = "echo hi",
    *,
    on_failure: str | FailureSpec = "abort",
) -> StepDefinition:
    # model_validate keeps string on_failure coercion without fighting the field type.
    return StepDefinition.model_validate(
        {
            "id": step_id,
            "type": StepType.COMMAND,
            "command": command,
            "on_failure": on_failure,
        }
    )


def _failed_result(step_id: str = "fail") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="nope",
        duration_seconds=0.01,
        error_message="boom",
    )


def _ok_result(step_id: str = "ok") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="completed",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.01,
    )


def make_run_context(
    fs: FileSystem,
    *,
    steps: list[StepDefinition] | None = None,
    **kwargs: Any,
) -> RunContext:
    """Build a RunContext with test-friendly defaults; override via kwargs."""
    defaults: dict[str, Any] = {
        "steps": steps if steps is not None else [_cmd_step("s1")],
        "cwd": fs.base_path,
        "use_sandbox": False,
    }
    defaults.update(kwargs)
    return RunContext(**defaults)


def patch_execute(
    monkeypatch: pytest.MonkeyPatch,
    behavior: Any = None,
) -> list[str]:
    """Patch engine.execute_step and return the list of executed step ids.

    ``behavior`` may be:
    - a StepResult (returned for every call, step_id rewritten)
    - an exception instance/class to raise
    - a callable(step) -> StepResult | BaseException
    - a dict keyed by step id: result, sequence of results (consumed in order),
      or callable(step)
    - None: succeed with ``_ok_result(step.id)``
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

    def fake_execute(
        step: StepDefinition,
        sandbox_path: Path,
        context: dict[str, Any] | None = None,
    ) -> StepResult:
        calls.append(step.id)
        resolved = _resolve_execute_behavior(step, behavior, queues)
        if isinstance(resolved, type) and issubclass(resolved, BaseException):
            raise resolved()
        if isinstance(resolved, BaseException):
            raise resolved
        return resolved

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)
    return calls


def _resolve_execute_behavior(
    step: StepDefinition,
    behavior: Any,
    queues: dict[str, list[StepResult]],
) -> StepResult | BaseException | type[BaseException]:
    if behavior is None:
        return _ok_result(step.id)
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
        return _ok_result(step.id)
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


def test_run_steps_success_no_sandbox(fs: FileSystem) -> None:
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("s1", "echo one"), _cmd_step("s2", "echo two")],
        )
    )

    assert outcome.ok is True
    assert len(outcome.step_results) == 2
    assert all(result.ok for result in outcome.step_results)
    assert outcome.sandbox_path == fs.base_path.resolve()
    assert outcome.sandbox_kept is False


def test_run_steps_success_with_sandbox(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    outcome = run_steps(
        make_run_context(
            git_fs,
            steps=[_cmd_step("s1", "echo sandboxed")],
            use_sandbox=True,
            keep=False,
        )
    )

    assert outcome.ok is True
    assert outcome.step_results[0].ok
    assert outcome.sandbox_kept is False
    assert not outcome.sandbox_path.exists()


def test_run_steps_abort_on_failure(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_execute(
        monkeypatch,
        {
            "fail": _failed_result(),
            "later": _ok_result(),
        },
    )
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step("fail", "exit 1", on_failure="abort"),
                _cmd_step("later", "echo should-not-run"),
            ],
        )
    )

    assert outcome.status == RunStatus.FAILED
    assert calls == ["fail"]
    assert len(outcome.step_results) == 1
    assert outcome.error_message == "Step 'fail' failed: boom"


def test_run_steps_continue_on_failure(fs: FileSystem) -> None:
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step("fail", "exit 1", on_failure="continue"),
                _cmd_step("ok", "echo recovered"),
            ],
        )
    )

    assert outcome.ok is True
    assert [r.status for r in outcome.step_results] == ["ignored", "completed"]


def test_run_steps_keep_sandbox(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    outcome = run_steps(
        make_run_context(
            git_fs,
            steps=[_cmd_step("s1", "echo keep-me")],
            use_sandbox=True,
            keep=True,
        )
    )

    assert outcome.ok is True
    assert outcome.sandbox_kept is True
    assert outcome.sandbox_path.is_dir()


def test_run_steps_observer_callbacks(fs: FileSystem) -> None:
    observer = MagicMock()
    outcome = run_steps(make_run_context(fs, observer=observer))

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


def test_run_steps_keyboard_interrupt(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_execute(monkeypatch, KeyboardInterrupt)
    outcome = run_steps(make_run_context(fs))

    assert outcome.status == RunStatus.CANCELLED
    assert outcome.error_message == "Execution cancelled by user."
    assert outcome.step_results == []


def test_run_steps_empty_steps(fs: FileSystem) -> None:
    outcome = run_steps(make_run_context(fs, steps=[]))

    assert outcome.ok is True
    assert outcome.step_results == []


def test_run_steps_sandbox_create_failure(fs: FileSystem) -> None:
    # No worktree init / config → sandbox create fails classified.
    outcome = run_steps(make_run_context(fs, use_sandbox=True))

    assert outcome.status == RunStatus.FAILED
    assert outcome.step_results == []
    assert outcome.error_message is not None
    assert "Git sandbox creation failed" in outcome.error_message


def test_run_steps_prompt_user_abort(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])
    calls = patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step("fail", on_failure="prompt_user"),
                _cmd_step("later"),
            ],
            failure_prompter=prompter,
        )
    )

    assert outcome.status == RunStatus.FAILED
    assert calls == ["fail"]
    assert prompter.calls == 1
    assert outcome.error_message == "Step 'fail' failed: boom"


def test_run_steps_prompt_user_continue(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])
    patch_execute(
        monkeypatch,
        {
            "fail": _failed_result(),
            "later": _ok_result(),
        },
    )
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step("fail", on_failure="prompt_user"),
                _cmd_step("later"),
            ],
            failure_prompter=prompter,
        )
    )

    assert outcome.ok is True
    assert outcome.step_results[0].status == "ignored"
    assert USER_CONTINUED_MARKER in (outcome.step_results[0].error_message or "")
    assert outcome.step_results[1].status == "completed"


def test_run_steps_prompt_user_retry_then_success(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.RETRY])
    calls = patch_execute(
        monkeypatch,
        {"fail": [_failed_result(), _ok_result()]},
    )
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("fail", on_failure="prompt_user")],
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
            {"non_interactive": True},
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
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
    ctx_kwargs: dict[str, Any],
    prompter: _BoomPrompter | None,
    warning_substr: str,
) -> None:
    patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("fail", on_failure="prompt_user")],
            failure_prompter=prompter,
            **ctx_kwargs,
        )
    )

    assert outcome.status == RunStatus.FAILED
    if prompter is not None:
        assert prompter.calls == 0
    assert any(warning_substr in w for w in outcome.warnings)


def test_run_steps_retry_exhausted_uses_on_max_retries_prompt(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])
    patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step(
                    "fail",
                    "exit 1",
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


def test_run_steps_persists_checkpoint_before_prompt(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryPauseStore()
    prompter = _AssertPausedPrompter(store)
    patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("fail", on_failure="prompt_user")],
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


def test_run_steps_non_interactive_never_pauses(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryPauseStore()
    patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("fail", on_failure="prompt_user")],
            non_interactive=True,
            pause_store=store,
        )
    )

    assert outcome.status == RunStatus.FAILED
    assert store.checkpoints == []
    assert store.cleared == 0


def test_run_steps_keyboard_interrupt_after_pause_keeps_paused(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryPauseStore()
    patch_execute(monkeypatch, _failed_result())
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[_cmd_step("fail", on_failure="prompt_user")],
            failure_prompter=_InterruptPrompter(),
            pause_store=store,
        )
    )

    assert outcome.status == RunStatus.PAUSED
    assert store.checkpoints
    assert store.cleared == 0
    assert outcome.sandbox_kept is True


def test_run_steps_resume_reprompts_and_skips_completed(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])
    calls = patch_execute(monkeypatch, {"later": _ok_result()})
    checkpoint = RunCheckpoint(
        next_step_index=1,
        step_results=[_ok_result("ok")],
        sandbox_path=str(fs.base_path),
        use_sandbox=False,
        keep=False,
        pending_step_id="fail",
        diagnostic="Step 'fail' failed: boom",
        pending_result=_failed_result("fail"),
    )
    outcome = run_steps(
        make_run_context(
            fs,
            steps=[
                _cmd_step("ok"),
                _cmd_step("fail", on_failure="prompt_user"),
                _cmd_step("later"),
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
