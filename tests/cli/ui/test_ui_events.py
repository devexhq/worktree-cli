"""Comprehensive tests for UI event models and formatters."""

from __future__ import annotations

import json

import pytest

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.run.observer import resolve_cli_observer
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
    output1 = buffer.getvalue()
    assert "Lock Held" in output1
    assert "PID: 12345" in output1
    assert "Waiting for lock release on '.lock'" in output1
    assert "30.0s" in output1

    # Without holder_pid
    buffer.seek(0)
    buffer.truncate(0)
    event2 = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid=None, timeout_seconds=15.0)
    dispatcher.dispatch(event2, output_format="terminal")
    output2 = buffer.getvalue()
    assert "Lock Held" in output2
    assert "PID:" not in output2
    assert "15.0s" in output2


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
