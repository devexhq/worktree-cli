"""Tests for CollapsingTailDisplay in worktree.cli.ui.tail."""

from __future__ import annotations

import io

from rich.console import Console
from rich.text import Text

from tests.helpers import make_dispatcher_with_buffer
from worktree.cli.ui.events import (
    MessageEvent,
    PromptEvent,
    PromptOption,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
)
from worktree.cli.ui.tail import _CURSOR_UP, _ERASE_LINE, CollapsingTailDisplay


def _create_display(
    *,
    tail_size: int = 3,
) -> tuple[CollapsingTailDisplay, io.StringIO, io.StringIO]:
    """Helper creating a CollapsingTailDisplay with string buffers for console and stream."""
    console_buffer = io.StringIO()
    console = Console(file=console_buffer, force_terminal=False, color_system=None, width=100)
    stream = io.StringIO()
    display = CollapsingTailDisplay(console, tail_size=tail_size, _stream=stream)
    return display, console_buffer, stream


def test_erase_tail_when_empty_does_not_write() -> None:
    display, _, stream = _create_display()
    display._erase_tail()
    assert stream.getvalue() == ""
    assert display._tail_height == 0


def test_erase_tail_when_non_empty_writes_ansi_sequence() -> None:
    display, _, stream = _create_display()
    display._tail_height = 2
    display._erase_tail()
    assert stream.getvalue() == (_CURSOR_UP + _ERASE_LINE) * 2
    assert display._tail_height == 0


def test_reprint_tail_writes_lines_and_updates_height() -> None:
    display, _, stream = _create_display(tail_size=3)
    display._tail.append("line 1")
    display._tail.append("line 2")
    display._reprint_tail()

    assert stream.getvalue() == "line 1\nline 2\n"
    assert display._tail_height == 2


def test_handle_step_start_prints_banner_with_name_and_command() -> None:
    display, console_buffer, stream = _create_display()
    display._tail.append("leftover")
    display._tail_height = 1

    event = StepStartEvent(idx=1, total=3, step_id="s1", name="Linting", command="ruff check")
    display.handle_step_start(event)

    assert stream.getvalue() == _CURSOR_UP + _ERASE_LINE
    assert len(display._tail) == 0
    assert display._tail_height == 0
    assert console_buffer.getvalue().strip() == "[1/3] Linting (ruff check)"


def test_handle_step_start_without_name_falls_back_to_step_id() -> None:
    display, console_buffer, _ = _create_display()

    event = StepStartEvent(idx=2, total=3, step_id="build-step", name=None, command=None)
    display.handle_step_start(event)

    assert console_buffer.getvalue().strip() == "[2/3] build-step"


def test_handle_step_output_appends_and_reprints() -> None:
    display, _, stream = _create_display(tail_size=2)

    display.handle_step_output(StepOutputEvent(step_id="s1", line="first line\n"))
    assert stream.getvalue() == "first line\n"
    assert display._tail_height == 1

    stream.seek(0)
    stream.truncate(0)

    display.handle_step_output(StepOutputEvent(step_id="s1", line="second line\r\n"))
    expected_output = (_CURSOR_UP + _ERASE_LINE) + "first line\nsecond line\n"
    assert stream.getvalue() == expected_output
    assert display._tail_height == 2


def test_handle_step_output_drops_old_lines_at_tail_capacity() -> None:
    display, _, stream = _create_display(tail_size=2)

    display.handle_step_output(StepOutputEvent(step_id="s1", line="line 1"))
    display.handle_step_output(StepOutputEvent(step_id="s1", line="line 2"))

    stream.seek(0)
    stream.truncate(0)

    display.handle_step_output(StepOutputEvent(step_id="s1", line="line 3"))
    expected_output = (_CURSOR_UP + _ERASE_LINE) * 2 + "line 2\nline 3\n"
    assert stream.getvalue() == expected_output
    assert list(display._tail) == ["line 2", "line 3"]
    assert display._tail_height == 2


def test_handle_step_done_success_erases_tail_and_prints_summary() -> None:
    display, console_buffer, stream = _create_display(tail_size=3)
    display._tail.append("some output")
    display._tail_height = 1

    event = StepDoneEvent(idx=1, total=2, step_id="step-1", ok=True, exit_code=0, duration_seconds=1.234)
    display.handle_step_done(event)

    assert stream.getvalue() == _CURSOR_UP + _ERASE_LINE
    assert len(display._tail) == 0
    assert display._tail_height == 0
    assert console_buffer.getvalue().strip() == "✔ [1/2] step-1  1.23s"


def test_handle_step_done_success_with_none_duration() -> None:
    display, console_buffer, _ = _create_display()

    event = StepDoneEvent(idx=1, total=1, step_id="step-1", ok=True, exit_code=0, duration_seconds=None)
    display.handle_step_done(event)

    assert console_buffer.getvalue().strip() == "✔ [1/1] step-1  0.00s"


def test_handle_step_done_failure_with_error_message() -> None:
    display, console_buffer, _ = _create_display()

    event = StepDoneEvent(
        idx=1,
        total=1,
        step_id="step-1",
        ok=False,
        exit_code=1,
        error_message="Process terminated with SIGKILL",
    )
    display.handle_step_done(event)

    assert console_buffer.getvalue().strip() == "✖ [1/1] step-1  Process terminated with SIGKILL"


def test_handle_step_done_failure_without_error_message() -> None:
    display, console_buffer, _ = _create_display()

    event = StepDoneEvent(
        idx=2,
        total=2,
        step_id="step-2",
        ok=False,
        exit_code=127,
        error_message=None,
    )
    display.handle_step_done(event)

    assert console_buffer.getvalue().strip() == "✖ [2/2] step-2  exit code 127"


def test_handle_sandbox_prints_above_active_tail() -> None:
    display, console_buffer, stream = _create_display(tail_size=3)
    display._tail.append("active line")
    display._tail_height = 1

    event = SandboxLifecycleEvent(action="ready", path="/path/to/sbx", active=True)
    rendered = Text("Sandbox: Active (/path/to/sbx)")
    display.handle_sandbox(event, rendered)

    assert console_buffer.getvalue().strip() == "Sandbox: Active (/path/to/sbx)"
    assert stream.getvalue() == (_CURSOR_UP + _ERASE_LINE) + "active line\n"
    assert display._tail_height == 1


def test_print_above_prints_renderable_above_active_tail() -> None:
    display, console_buffer, stream = _create_display(tail_size=3)
    display._tail.append("active line")
    display._tail_height = 1

    display.print_above(Text("Important notice"))

    assert console_buffer.getvalue().strip() == "Important notice"
    assert stream.getvalue() == (_CURSOR_UP + _ERASE_LINE) + "active line\n"
    assert display._tail_height == 1


def test_dispatcher_start_collapsing_tail_when_interactive_and_terminal() -> None:
    dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True, output_format="terminal")
    assert dispatcher._tail_display is None

    dispatcher.start_collapsing_tail()
    assert dispatcher._tail_display is not None

    active_instance = dispatcher._tail_display
    dispatcher.start_collapsing_tail()
    assert dispatcher._tail_display is active_instance


def test_dispatcher_start_collapsing_tail_guards() -> None:
    dispatcher_non_tty, _ = make_dispatcher_with_buffer(force_terminal=False, output_format="terminal")
    dispatcher_non_tty.start_collapsing_tail()
    assert dispatcher_non_tty._tail_display is None

    dispatcher_json, _ = make_dispatcher_with_buffer(force_terminal=True, output_format="json")
    dispatcher_json.start_collapsing_tail()
    assert dispatcher_json._tail_display is None


def test_dispatcher_stop_collapsing_tail() -> None:
    dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
    dispatcher.start_collapsing_tail()
    assert dispatcher._tail_display is not None

    dispatcher.stop_collapsing_tail()
    assert dispatcher._tail_display is None


def test_dispatcher_collapsing_tail_event_routing() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    dispatcher.start_collapsing_tail()
    assert dispatcher._tail_display is not None

    stream = io.StringIO()
    dispatcher._tail_display._stream = stream

    dispatcher.dispatch(StepStartEvent(idx=1, total=1, step_id="s1", name="lint", command="ruff check"))
    dispatcher.dispatch(StepOutputEvent(step_id="s1", line="all clean"))
    dispatcher.dispatch(SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True))
    dispatcher.dispatch(MessageEvent(message="Advisory notice"))
    dispatcher.dispatch(StepDoneEvent(idx=1, total=1, step_id="s1", ok=True, exit_code=0, duration_seconds=0.25))

    console_output = buffer.getvalue()
    assert "[1/1] lint (ruff check)" in console_output
    assert "Sandbox: Active (/tmp/sbx)" in console_output
    assert "Advisory notice" in console_output
    assert "[1/1] s1  0.25s" in console_output
    assert "✔" in console_output
    assert "all clean\n" in stream.getvalue()


def test_dispatcher_collapsing_tail_prompt_stops_tail() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    dispatcher.start_collapsing_tail()
    assert dispatcher._tail_display is not None

    prompt = PromptEvent(
        prompt_type="step_failure",
        prompt_id="s1",
        kind="task",
        title="Step Failed",
        options=[PromptOption(key="a", label="Abort", decision="abort")],
    )
    dispatcher.dispatch(prompt)

    assert dispatcher._tail_display is None
    assert "Step Failed" in buffer.getvalue()
