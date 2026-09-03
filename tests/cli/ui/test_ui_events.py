"""Comprehensive tests for UI event models, formatters, and DispatcherRunObserver."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from worktree.cli.run.observer import DispatcherRunObserver, resolve_cli_observer
from worktree.cli.ui.dispatcher import UiDispatcher
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
from worktree.core.db import BlueprintKind, RunStatus
from worktree.core.step import ConditionEvaluationResult, StepDefinition, StepResult


@pytest.fixture
def dispatcher_with_buf() -> tuple[UiDispatcher, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)
    dispatcher = UiDispatcher(console=console)
    register_ui_formatters(dispatcher)
    return dispatcher, buf


def test_error_panel_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = ErrorPanelEvent(title="Task Run Failed", message="Command failed with exit code 1.")
    dispatcher.dispatch(event, output_format="terminal")
    output = buf.getvalue()
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


def test_warning_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = WarningEvent(message="Something non-fatal occurred.")
    dispatcher.dispatch(event, output_format="terminal")
    assert "Warning: Something non-fatal occurred." in buf.getvalue()


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


def test_lock_wait_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event1 = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid="12345", timeout_seconds=30.0)
    dispatcher.dispatch(event1, output_format="terminal")
    out1 = buf.getvalue()
    assert "Lock Held" in out1
    assert "PID: 12345" in out1
    assert "Waiting for lock release on '.lock'" in out1
    assert "30.0s" in out1

    # Without holder_pid
    buf.seek(0)
    buf.truncate(0)
    event2 = LockWaitEvent(lock_path="/path/to/.worktree/.lock", holder_pid=None, timeout_seconds=15.0)
    dispatcher.dispatch(event2, output_format="terminal")
    out2 = buf.getvalue()
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


def test_message_event_terminal_and_styled(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event1 = MessageEvent(message="Running task 'build'...")
    dispatcher.dispatch(event1, output_format="terminal")
    assert "Running task 'build'..." in buf.getvalue()

    event2 = MessageEvent(message="Styled notice", style="bold")
    dispatcher.dispatch(event2, output_format="terminal")
    assert "Styled notice" in buf.getvalue()


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


def test_run_success_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = RunSuccessEvent(
        session_id="task_12345678",
        blueprint_name="build",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )
    dispatcher.dispatch(event, output_format="terminal")
    output = buf.getvalue()
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


def test_step_start_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = StepStartEvent(
        idx=1,
        total=3,
        step_id="build",
        name="Compile Assets",
        command="cargo build",
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 1/3] Executing Compile Assets (command: cargo build)..." in buf.getvalue()


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


def test_step_done_event_terminal_success(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = StepDoneEvent(
        idx=1,
        total=1,
        step_id="build",
        ok=True,
        exit_code=0,
        duration_seconds=1.23,
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 1/1] build COMPLETED" in buf.getvalue()


def test_step_done_event_terminal_failure(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = StepDoneEvent(
        idx=2,
        total=2,
        step_id="test",
        ok=False,
        exit_code=1,
        error_message="Assertion failed",
    )
    dispatcher.dispatch(event, output_format="terminal")
    assert "[STEP 2/2] test FAILED: Assertion failed" in buf.getvalue()


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


def test_step_output_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    event = StepOutputEvent(step_id="build", line="compiling crate...", stream="stdout")
    dispatcher.dispatch(event, output_format="terminal")
    assert "compiling crate..." in buf.getvalue()


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


def test_sandbox_lifecycle_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    # Ready active
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True),
        output_format="terminal",
    )
    assert "Sandbox: Active (/tmp/sbx)" in buf.getvalue()

    # Ready in-place
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="ready", path="/workspace", active=False),
        output_format="terminal",
    )
    assert "Sandbox: In-place (workspace)" in buf.getvalue()

    # Cleanup retained
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=True),
        output_format="terminal",
    )
    assert "Sandbox: Retained (/tmp/sbx)" in buf.getvalue()

    # Cleanup removed
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=False),
        output_format="terminal",
    )
    assert "Sandbox: Cleaned" in buf.getvalue()


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


def test_loop_lifecycle_event_terminal(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
    # Start
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="start", max_iterations=5),
        output_format="terminal",
    )
    assert "[loop_1] Starting loop block (max_iterations: 5)" in buf.getvalue()

    # Turn start
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="turn_start", turn=2, max_iterations=5),
        output_format="terminal",
    )
    assert "[loop_1] --- Iteration Turn 2/5 ---" in buf.getvalue()

    # Conditions evaluated
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="conditions_evaluated", message="Evaluated conditions"),
        output_format="terminal",
    )
    assert "Evaluated conditions" in buf.getvalue()

    # Done completed
    buf.seek(0)
    buf.truncate(0)
    dispatcher.dispatch(
        LoopLifecycleEvent(loop_id="loop_1", action="done", turn=3, status="completed"),
        output_format="terminal",
    )
    assert "[loop_1] Loop completed successfully in 3 iteration(s)." in buf.getvalue()


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


def test_dispatcher_run_observer_callbacks(dispatcher_with_buf: tuple[UiDispatcher, io.StringIO]) -> None:
    dispatcher, buf = dispatcher_with_buf
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

    output = buf.getvalue()
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
    buf = io.StringIO()
    console_non_tty = Console(file=buf, force_terminal=False)
    dispatcher_non_tty = UiDispatcher(console=console_non_tty)
    obs_terminal_non_tty = resolve_cli_observer(dispatcher_non_tty, output_format="terminal")
    assert isinstance(obs_terminal_non_tty, DispatcherRunObserver)
    assert obs_terminal_non_tty._live is False

    # tty console in terminal mode -> DispatcherRunObserver with live=True
    console_tty = Console(file=buf, force_terminal=True)
    dispatcher_tty = UiDispatcher(console=console_tty)
    obs_terminal_tty = resolve_cli_observer(dispatcher_tty, output_format="terminal")
    assert isinstance(obs_terminal_tty, DispatcherRunObserver)
    assert obs_terminal_tty._live is True


def test_dispatcher_format_and_interactive_properties() -> None:
    buf = io.StringIO()
    console_tty = Console(file=buf, force_terminal=True)
    dispatcher_tty = UiDispatcher(console=console_tty, output_format="terminal")
    assert dispatcher_tty.is_interactive is True
    assert dispatcher_tty.is_terminal_format is True
    assert dispatcher_tty.console is console_tty

    # If output_format is json, is_interactive is True but is_terminal_format is False
    dispatcher_tty.set_output_format("json")
    assert dispatcher_tty.is_interactive is True
    assert dispatcher_tty.is_terminal_format is False

    console_non_tty = Console(file=buf, force_terminal=False)
    dispatcher_non_tty = UiDispatcher(console=console_non_tty, output_format="terminal")
    assert dispatcher_non_tty.is_interactive is False
    assert dispatcher_non_tty.is_terminal_format is True


def test_dispatcher_live_mode_routing() -> None:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True)
    dispatcher = UiDispatcher(console=console)
    register_ui_formatters(dispatcher)
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
    output = buf.getvalue()
    assert "Sandbox: Active (/tmp/sbx)" in output
    assert "[l1] Starting loop block (max_iterations: 2)" in output
