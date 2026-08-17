"""Unit/integration tests for the shared run_steps engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers import FileSystem, GitFileSystem
from worktree.core.db import RunStatus
from worktree.core.runtime import (
    USER_CONTINUED_MARKER,
    FailurePromptDecision,
    RunContext,
    run_steps,
)
from worktree.core.step import FailurePolicy, FailureSpec, StepDefinition, StepResult, StepType


def _cmd_step(step_id: str, command: str, *, on_failure: str = "abort") -> StepDefinition:
    return StepDefinition(
        id=step_id,
        type=StepType.COMMAND,
        command=command,
        on_failure=on_failure,
    )


def test_run_steps_success_no_sandbox(fs: FileSystem) -> None:
    context = RunContext(
        steps=[_cmd_step("s1", "echo one"), _cmd_step("s2", "echo two")],
        cwd=fs.base_path,
        use_sandbox=False,
    )

    outcome = run_steps(context)

    assert outcome.ok is True
    assert outcome.status == RunStatus.COMPLETED
    assert len(outcome.step_results) == 2
    assert all(result.ok for result in outcome.step_results)
    assert outcome.sandbox_path == fs.base_path.resolve()
    assert outcome.sandbox_kept is False
    assert outcome.error_message is None


def test_run_steps_success_with_sandbox(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    context = RunContext(
        steps=[_cmd_step("s1", "echo sandboxed")],
        cwd=git_fs.base_path,
        use_sandbox=True,
        keep=False,
    )

    outcome = run_steps(context)

    assert outcome.ok is True
    assert outcome.status == RunStatus.COMPLETED
    assert len(outcome.step_results) == 1
    assert outcome.step_results[0].ok
    assert outcome.sandbox_kept is False
    assert not outcome.sandbox_path.exists()


def test_run_steps_abort_on_failure(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_execute(
        step: StepDefinition,
        sandbox_path: Path,
        context: dict | None = None,
    ) -> StepResult:
        calls.append(step.id)
        if step.id == "fail":
            return StepResult(
                step_id=step.id,
                status="failed",
                exit_code=1,
                stdout="",
                stderr="nope",
                duration_seconds=0.01,
                error_message="boom",
            )
        return StepResult(
            step_id=step.id,
            status="completed",
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_seconds=0.01,
        )

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[
            _cmd_step("fail", "exit 1", on_failure="abort"),
            _cmd_step("later", "echo should-not-run"),
        ],
        cwd=fs.base_path,
        use_sandbox=False,
    )

    outcome = run_steps(context)

    assert outcome.ok is False
    assert outcome.status == RunStatus.FAILED
    assert calls == ["fail"]
    assert len(outcome.step_results) == 1
    assert outcome.error_message == "Step 'fail' failed: boom"


def test_run_steps_continue_on_failure(fs: FileSystem) -> None:
    context = RunContext(
        steps=[
            _cmd_step("fail", "exit 1", on_failure="continue"),
            _cmd_step("ok", "echo recovered"),
        ],
        cwd=fs.base_path,
        use_sandbox=False,
    )

    outcome = run_steps(context)

    assert outcome.ok is True
    assert outcome.status == RunStatus.COMPLETED
    assert len(outcome.step_results) == 2
    assert outcome.step_results[0].status == "ignored"
    assert outcome.step_results[1].status == "completed"
    assert outcome.error_message is None


def test_run_steps_keep_sandbox(git_fs: GitFileSystem) -> None:
    git_fs.init_repo()
    context = RunContext(
        steps=[_cmd_step("s1", "echo keep-me")],
        cwd=git_fs.base_path,
        use_sandbox=True,
        keep=True,
    )

    outcome = run_steps(context)

    assert outcome.ok is True
    assert outcome.sandbox_kept is True
    assert outcome.sandbox_path.is_dir()


def test_run_steps_observer_callbacks(fs: FileSystem) -> None:
    observer = MagicMock()
    steps = [_cmd_step("s1", "echo hi")]
    context = RunContext(
        steps=steps,
        cwd=fs.base_path,
        use_sandbox=False,
        observer=observer,
    )

    outcome = run_steps(context)

    assert outcome.ok is True
    observer.on_sandbox_ready.assert_called_once_with(fs.base_path.resolve(), False)
    observer.on_step_start.assert_called_once()
    start_args = observer.on_step_start.call_args.args
    assert start_args[0] == 1
    assert start_args[1] == 1
    assert start_args[2].id == "s1"
    observer.on_step_done.assert_called_once()
    done_args = observer.on_step_done.call_args.args
    assert done_args[0] == 1
    assert done_args[1] == 1
    assert isinstance(done_args[2], StepResult)
    observer.on_sandbox_cleanup.assert_called_once_with(False, fs.base_path.resolve())


def test_run_steps_keyboard_interrupt(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    import worktree.core.runtime.engine as engine_mod

    def raise_interrupt(
        step: StepDefinition,
        sandbox_path: Path,
        context: dict | None = None,
    ) -> StepResult:
        raise KeyboardInterrupt

    monkeypatch.setattr(engine_mod, "execute_step", raise_interrupt)

    context = RunContext(
        steps=[_cmd_step("s1", "echo never")],
        cwd=fs.base_path,
        use_sandbox=False,
    )

    outcome = run_steps(context)

    assert outcome.status == RunStatus.CANCELLED
    assert outcome.ok is False
    assert outcome.error_message == "Execution cancelled by user."
    assert outcome.step_results == []


def test_run_steps_empty_steps(fs: FileSystem) -> None:
    context = RunContext(steps=[], cwd=fs.base_path, use_sandbox=False)

    outcome = run_steps(context)

    assert outcome.ok is True
    assert outcome.status == RunStatus.COMPLETED
    assert outcome.step_results == []


def test_run_steps_sandbox_create_failure(fs: FileSystem) -> None:
    # No worktree init / config → sandbox create fails classified.
    context = RunContext(
        steps=[_cmd_step("s1", "echo hi")],
        cwd=fs.base_path,
        use_sandbox=True,
    )

    outcome = run_steps(context)

    assert outcome.ok is False
    assert outcome.status == RunStatus.FAILED
    assert outcome.step_results == []
    assert outcome.error_message is not None
    assert "Git sandbox creation failed" in outcome.error_message


class _ScriptedPrompter:
    def __init__(self, decisions: list) -> None:
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


def _ok_result(step_id: str = "fail") -> StepResult:
    return StepResult(
        step_id=step_id,
        status="completed",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.01,
    )


def test_run_steps_prompt_user_abort(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])
    calls: list[str] = []

    def fake_execute(step, sandbox_path, context=None):
        calls.append(step.id)
        return _failed_result(step.id)

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[
            _cmd_step("fail", "exit 1", on_failure="prompt_user"),
            _cmd_step("later", "echo no"),
        ],
        cwd=fs.base_path,
        use_sandbox=False,
        failure_prompter=prompter,
    )
    outcome = run_steps(context)
    assert outcome.status == RunStatus.FAILED
    assert calls == ["fail"]
    assert prompter.calls == 1
    assert outcome.error_message == "Step 'fail' failed: boom"


def test_run_steps_prompt_user_continue(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.CONTINUE])

    def fake_execute(step, sandbox_path, context=None):
        if step.id == "fail":
            return _failed_result("fail")
        return _ok_result(step.id)

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[
            _cmd_step("fail", "exit 1", on_failure="prompt_user"),
            _cmd_step("later", "echo yes"),
        ],
        cwd=fs.base_path,
        use_sandbox=False,
        failure_prompter=prompter,
    )
    outcome = run_steps(context)
    assert outcome.ok is True
    assert outcome.step_results[0].status == "ignored"
    assert USER_CONTINUED_MARKER in (outcome.step_results[0].error_message or "")
    assert outcome.step_results[1].status == "completed"


def test_run_steps_prompt_user_retry_then_success(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.RETRY])
    attempts = {"fail": 0}

    def fake_execute(step, sandbox_path, context=None):
        if step.id != "fail":
            return _ok_result(step.id)
        attempts["fail"] += 1
        if attempts["fail"] == 1:
            return _failed_result("fail")
        return _ok_result("fail")

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[_cmd_step("fail", "exit 1", on_failure="prompt_user")],
        cwd=fs.base_path,
        use_sandbox=False,
        failure_prompter=prompter,
    )
    outcome = run_steps(context)
    assert outcome.ok is True
    assert attempts["fail"] == 2
    assert prompter.calls == 1
    assert outcome.step_results[0].status == "completed"


def test_run_steps_prompt_user_non_interactive_aborts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    class BoomPrompter:
        def prompt_step_failure(self, **kwargs):
            called["n"] += 1
            raise AssertionError("should not prompt")

    def fake_execute(step, sandbox_path, context=None):
        return _failed_result(step.id)

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[_cmd_step("fail", "exit 1", on_failure="prompt_user")],
        cwd=fs.base_path,
        use_sandbox=False,
        non_interactive=True,
        failure_prompter=BoomPrompter(),
    )
    outcome = run_steps(context)
    assert outcome.status == RunStatus.FAILED
    assert called["n"] == 0
    assert any("non-interactive" in w for w in outcome.warnings)


def test_run_steps_prompt_user_default_no_prompter_aborts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute(step, sandbox_path, context=None):
        return _failed_result(step.id)

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    context = RunContext(
        steps=[_cmd_step("fail", "exit 1", on_failure="prompt_user")],
        cwd=fs.base_path,
        use_sandbox=False,
    )
    outcome = run_steps(context)
    assert outcome.status == RunStatus.FAILED
    assert any("no failure prompter" in w for w in outcome.warnings)


def test_run_steps_retry_exhausted_uses_on_max_retries_prompt(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    prompter = _ScriptedPrompter([FailurePromptDecision.ABORT])

    def fake_execute(step, sandbox_path, context=None):
        return _failed_result(step.id)

    import worktree.core.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "execute_step", fake_execute)

    step = StepDefinition(
        id="fail",
        type=StepType.COMMAND,
        command="exit 1",
        on_failure=FailureSpec(
            action=FailurePolicy.RETRY,
            max_retries=2,
            on_max_retries=FailurePolicy.PROMPT_USER,
        ),
    )
    context = RunContext(
        steps=[step],
        cwd=fs.base_path,
        use_sandbox=False,
        failure_prompter=prompter,
    )
    outcome = run_steps(context)
    assert outcome.status == RunStatus.FAILED
    assert prompter.calls == 1
