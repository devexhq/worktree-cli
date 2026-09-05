"""Comprehensive tests for UI event models, formatters, and DispatcherRunObserver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.run.observer import DispatcherRunObserver, resolve_cli_observer
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.events import (
    ErrorPanelEvent,
    LockWaitEvent,
    LoopLifecycleEvent,
    MessageEvent,
    RunSuccessEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
    WarningEvent,
)
from worktree.cli.ui.formatters import register_ui_formatters
from worktree.cli.ui.formatters.events import LockWaitFormatter
from worktree.core.db import BlueprintKind, RunStatus
from worktree.core.step import ConditionEvaluationResult, StepDefinition, StepResult


def test_error_panel_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = ErrorPanelEvent(title="Task Run Failed", message="Command failed with exit code 1.")
    dispatcher.dispatch(event, output_format="terminal")
    output = buffer.getvalue()
    assert "Task Run Failed" in output
    assert "Command failed with exit code 1." in output


def test_error_panel_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = ErrorPanelEvent(title="Task Run Failed", message="Command failed with exit code 1.")
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "ErrorPanelEvent",
        "payload": {
            "title": "Task Run Failed",
            "message": "Command failed with exit code 1.",
            "border_style": "red",
        },
    }


def test_warning_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = WarningEvent(message="Something non-fatal occurred.")
    dispatcher.dispatch(event, output_format="terminal")
    assert "Warning: Something non-fatal occurred." in buffer.getvalue()


def test_warning_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = WarningEvent(message="Something non-fatal occurred.")
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "WarningEvent",
        "payload": {"message": "Something non-fatal occurred."},
    }


def test_lock_wait_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event1 = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid="12345", timeout_seconds=30.0)
    dispatcher.dispatch(event1, output_format="terminal")
    out1 = buffer.getvalue()
    assert "Lock Held" in out1
    assert "PID: 12345" in out1
    assert "Waiting for lock release on '.lock'" in out1
    assert "30.0s" in out1

    # Without holder_pid
    buffer.seek(0)
    buffer.truncate(0)
    event2 = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid=None, timeout_seconds=15.0)
    dispatcher.dispatch(event2, output_format="terminal")
    out2 = buffer.getvalue()
    assert "Lock Held" in out2
    assert "PID:" not in out2
    assert "15.0s" in out2


def test_lock_wait_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid="999", timeout_seconds=30.0)
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "LockWaitEvent",
        "payload": {
            "lock_path": "/path/to/.worktree/.lock",
            "holder_pid": "999",
            "timeout_seconds": 30.0,
        },
    }


class LockWaitFormatterTests:
    """Tier 2 presentation contract tests for LockWaitFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid="12345",
            timeout_seconds=30.0,
        )
        assert formatter.to_json_serializable(event) == {
            "lock_path": "/path/to/.worktree/.lock",
            "holder_pid": "12345",
            "timeout_seconds": 30.0,
        }

    def test_to_rich_with_holder_pid_contains_model_values(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid="12345",
            timeout_seconds=30.0,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "12345" in rendered
        assert ".lock" in rendered
        assert "30.0s" in rendered

    def test_to_rich_without_holder_pid_contains_model_values(self) -> None:
        formatter = LockWaitFormatter()
        event = LockWaitEvent(
            lock_path="/path/to/.worktree/.lock",
            holder_pid=None,
            timeout_seconds=15.0,
        )
        rendered = render_rich(formatter.to_rich(event))
        assert "PID:" not in rendered
        assert ".lock" in rendered
        assert "15.0s" in rendered

    def test_ui_dispatcher_registration(self) -> None:
        assert LockWaitEvent in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[LockWaitEvent], LockWaitFormatter)


def test_message_event_terminal_and_styled() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event1 = MessageEvent(message="Running task 'build'...")
    dispatcher.dispatch(event1, output_format="terminal")
    assert "Running task 'build'..." in buffer.getvalue()

    event2 = MessageEvent(message="Styled notice", style="bold")
    dispatcher.dispatch(event2, output_format="terminal")
    assert "Styled notice" in buffer.getvalue()


def test_message_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = MessageEvent(message="Running task 'build'...", style="dim")
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "MessageEvent",
        "payload": {"message": "Running task 'build'...", "style": "dim"},
    }


def test_run_success_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = RunSuccessEvent(
        session_id="task_12345678",
        blueprint_name="build",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )
    dispatcher.dispatch(event, output_format="terminal")
    output = buffer.getvalue()
    assert "Task Run Completed:" in output
    assert "build" in output
    assert "session: task_12345678" in output
    assert "status: completed" in output


def test_run_success_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = RunSuccessEvent(
        session_id="wf_12345678",
        blueprint_name="deploy",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
    )
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "RunSuccessEvent",
        "payload": {
            "session_id": "wf_12345678",
            "blueprint_name": "deploy",
            "kind": "workflow",
            "status": "completed",
        },
    }


def test_step_start_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = StepStartEvent(
        idx=1,
        total=3,
        step_id="build",
        name="Compile Assets",
        command="cargo build",
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 1/3] Executing Compile Assets (command: cargo build)..." in buffer.getvalue()


def test_step_start_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = StepStartEvent(
        idx=1,
        total=2,
        step_id="lint",
    )
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "StepStartEvent",
        "payload": {
            "idx": 1,
            "total": 2,
            "step_id": "lint",
            "name": None,
            "command": None,
        },
    }


def test_step_done_event_terminal_success() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = StepDoneEvent(
        idx=1,
        total=1,
        step_id="build",
        ok=True,
        exit_code=0,
        duration_seconds=1.23,
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 1/1] build COMPLETED" in buffer.getvalue()


def test_step_done_event_terminal_failure() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = StepDoneEvent(
        idx=2,
        total=2,
        step_id="test",
        ok=False,
        exit_code=1,
        error_message="Assertion failed",
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 2/2] test FAILED: Assertion failed" in buffer.getvalue()


def test_step_done_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = StepDoneEvent(
        idx=1,
        total=1,
        step_id="build",
        ok=True,
        exit_code=0,
        duration_seconds=0.5,
    )
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "StepDoneEvent",
        "payload": {
            "idx": 1,
            "total": 1,
            "step_id": "build",
            "ok": True,
            "exit_code": 0,
            "duration_seconds": 0.5,
            "error_message": None,
        },
    }


def test_step_output_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    event = StepOutputEvent(step_id="build", line="compiling crate...", stream="stdout")
    dispatcher.dispatch(event, output_format="terminal")
    assert "compiling crate..." in buffer.getvalue()


def test_step_output_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = StepOutputEvent(step_id="build", line="compiling crate...", stream="stdout")
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "StepOutputEvent",
        "payload": {
            "step_id": "build",
            "line": "compiling crate...",
            "stream": "stdout",
        },
    }


def test_sandbox_lifecycle_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    # Ready active
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True),
        output_format="terminal",
    )
    assert "Sandbox: Active (/tmp/sbx)" in buffer.getvalue()

    # Ready in-place
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="ready", path="/workspace", active=False),
        output_format="terminal",
    )
    assert "Sandbox: In-place (workspace)" in buffer.getvalue()

    # Cleanup retained
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=True),
        output_format="terminal",
    )
    assert "Sandbox: Retained (/tmp/sbx)" in buffer.getvalue()

    # Cleanup removed
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=False),
        output_format="terminal",
    )
    assert "Sandbox: Cleaned" in buffer.getvalue()


def test_sandbox_lifecycle_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = SandboxLifecycleEvent(action="ready", path="/workspace", active=False)
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "SandboxLifecycleEvent",
        "payload": {
            "action": "ready",
            "path": "/workspace",
            "active": False,
            "kept": None,
        },
    }


def test_loop_lifecycle_event_terminal() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    # Start
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="start", max_iterations=5),
        output_format="terminal",
    )
    assert "[loop_1] Starting loop block (max_iterations: 5)" in buffer.getvalue()

    # Turn start
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="turn_start", turn=2, max_iterations=5),
        output_format="terminal",
    )
    assert "[loop_1] --- Iteration Turn 2/5 ---" in buffer.getvalue()

    # Conditions evaluated
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="conditions_evaluated", message="Evaluated conditions"),
        output_format="terminal",
    )
    assert "Evaluated conditions" in buffer.getvalue()

    # Done completed
    buffer.seek(0)
    buffer.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="done", turn=3, status="completed"),
        output_format="terminal",
    )
    assert "[loop_1] Loop completed successfully in 3 iteration(s)." in buffer.getvalue()


def test_loop_lifecycle_event_json(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_ui_formatters(dispatcher)
    event = LoopLifecycleEvent(
        loop_id="loop_1",
        action="turn_start",
        turn=1,
        max_iterations=3,
    )
    dispatcher.dispatch(event, output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "LoopLifecycleEvent",
        "payload": {
            "loop_id": "loop_1",
            "action": "turn_start",
            "turn": 1,
            "max_iterations": 3,
            "status": None,
            "message": None,
        },
    }


def test_dispatcher_run_observer_callbacks() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    observer = DispatcherRunObserver(dispatcher)

    with observer:
        observer.on_sandbox_ready(Path("/tmp/sbx"), active=True)
        observer.on_step_start(1, 2, StepDefinition(id="step-1", run="echo 1", name="First Step"))
        observer.on_step_output(1, 2, StepDefinition(id="step-1", run="echo 1"), "output line 1")
        observer.on_step_done(
            1,
            2,
            StepResult(
                step_id="step-1",
                status="completed",
                exit_code=0,
                stdout="output line 1",
                stderr="",
                duration_seconds=0.1,
            ),
        )
        observer.on_loop_start("loop-test", 4)
        observer.on_loop_turn_start("loop-test", 1, 4)
        observer.on_loop_conditions_evaluated(
            "loop-test",
            [ConditionEvaluationResult(expression="exit_code == 0", passed=True, detail="exit_code is 0")],
            all_passed=True,
        )
        observer.on_loop_done("loop-test", "completed", 1)
        observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx"))

    output = buffer.getvalue()
    assert "Sandbox: Active (/tmp/sbx)" in output
    assert "[STEP 1/2] Executing First Step (command: echo 1)..." in output
    assert "output line 1" in output
    assert "[STEP 1/2] step-1 COMPLETED" in output
    assert "[loop-test] Starting loop block (max_iterations: 4)" in output
    assert "[loop-test] --- Iteration Turn 1/4 ---" in output
    assert "Evaluated 'until' conditions:" in output
    assert "[loop-test] Loop completed successfully in 1 iteration(s)." in output
    assert "Sandbox: Cleaned" in output


def test_resolve_cli_observer() -> None:
    dispatcher = UiDispatcher()
    # JSON mode -> DispatcherRunObserver with live=False
    obs_json = resolve_cli_observer(dispatcher, output_format="json")
    assert isinstance(obs_json, DispatcherRunObserver)
    assert obs_json._live is False

    # non-interactive -> DispatcherRunObserver with live=False
    obs_non_interactive = resolve_cli_observer(dispatcher, non_interactive=True)
    assert isinstance(obs_non_interactive, DispatcherRunObserver)
    assert obs_non_interactive._live is False

    # non-tty console in terminal mode -> DispatcherRunObserver with live=False
    dispatcher_non_tty, _ = make_dispatcher_with_buffer(force_terminal=False)
    obs_terminal_non_tty = resolve_cli_observer(dispatcher_non_tty, output_format="terminal")
    assert isinstance(obs_terminal_non_tty, DispatcherRunObserver)
    assert obs_terminal_non_tty._live is False

    # tty console in terminal mode -> DispatcherRunObserver with live=True
    dispatcher_tty, _ = make_dispatcher_with_buffer(force_terminal=True)
    obs_terminal_tty = resolve_cli_observer(dispatcher_tty, output_format="terminal")
    assert isinstance(obs_terminal_tty, DispatcherRunObserver)
    assert obs_terminal_tty._live is True


def test_resolve_cli_observer_live_mode_emits_output() -> None:
    """Verify resolve_cli_observer with live=True emits step, sandbox, and loop lifecycle output."""
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    observer = resolve_cli_observer(dispatcher, output_format="terminal")
    assert observer._live is True

    with observer:
        observer.on_sandbox_ready(Path("/tmp/sbx_live"), active=True)
        observer.on_step_start(1, 2, StepDefinition(id="step-1", run="echo live", name="Live Step"))
        observer.on_step_output(1, 2, StepDefinition(id="step-1", run="echo live"), "streaming output")
        observer.on_step_done(
            1,
            2,
            StepResult(
                step_id="step-1",
                status="completed",
                exit_code=0,
                stdout="streaming output",
                stderr="",
                duration_seconds=0.2,
            ),
        )
        observer.on_loop_start("loop-live", 3)
        observer.on_loop_turn_start("loop-live", 1, 3)
        observer.on_loop_conditions_evaluated(
            "loop-live",
            [ConditionEvaluationResult(expression="exit_code == 0", passed=False, detail="exit_code is 1")],
            all_passed=False,
            next_turn=2,
        )
        observer.on_loop_turn_start("loop-live", 2, 3)
        observer.on_loop_conditions_evaluated(
            "loop-live",
            [ConditionEvaluationResult(expression="exit_code == 0", passed=True, detail="exit_code is 0")],
            all_passed=True,
        )
        observer.on_loop_done("loop-live", "completed", 2)
        observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx_live"))

    output = buffer.getvalue()
    assert "/tmp/sbx_live" in output
    assert "Live Step" in output
    assert "echo live" in output
    assert "loop-live" in output
    assert "Conditions not met. Continuing to turn 2" in output
    assert "Sandbox: Cleaned" in output


def test_dispatcher_format_and_interactive_properties() -> None:
    dispatcher_tty, _ = make_dispatcher_with_buffer(force_terminal=True, output_format="terminal")
    assert dispatcher_tty.is_interactive is True
    assert dispatcher_tty.is_terminal_format is True

    # If output_format is json, is_interactive is True but is_terminal_format is False
    dispatcher_tty.set_output_format("json")
    assert dispatcher_tty.is_interactive is True
    assert dispatcher_tty.is_terminal_format is False

    dispatcher_non_tty, _ = make_dispatcher_with_buffer(force_terminal=False, output_format="terminal")
    assert dispatcher_non_tty.is_interactive is False
    assert dispatcher_non_tty.is_terminal_format is True


def test_dispatcher_live_mode_routing() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    observer = resolve_cli_observer(dispatcher, output_format="terminal")

    with observer:
        assert dispatcher._live_display is not None
        assert dispatcher._live_display.is_active

        dispatcher.dispatch(StepStartEvent(idx=1, total=1, step_id="s1", name="lint", command="ruff"))
        dispatcher.dispatch(StepOutputEvent(step_id="s1", line="all clean"))
        dispatcher.dispatch(StepDoneEvent(idx=1, total=1, step_id="s1", ok=True, exit_code=0, duration_seconds=0.1))
        dispatcher.dispatch(SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True))
        dispatcher.dispatch(LoopLifecycleEvent(loop_id="l1", action="start", max_iterations=2))

    assert dispatcher._live_display is None
    output = buffer.getvalue()
    assert "Sandbox: Active (/tmp/sbx)" in output
    assert "[l1] Starting loop block (max_iterations: 2)" in output
