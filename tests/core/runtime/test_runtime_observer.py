"""Unit tests for runtime execution observers and live tail panel renderers."""

from __future__ import annotations

from collections import deque
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from tests.helpers import (
    RichOutput,
    make_cmd_step,
    make_failed_result,
    make_ok_result,
    make_rich_output,
)
from worktree.cli.run.observer import (
    DEFAULT_OUTPUT_BUFFER_SIZE,
    CliRunObserver,
    LiveRunObserver,
    LiveStepItem,
    _format_failure_detail,
    _format_step_elapsed,
    _format_step_glyph,
    _resolve_step_duration,
    build_live_output_panel,
    build_live_renderable,
    build_live_step_table,
    resolve_run_observer,
)
from worktree.core.runtime.engine import _notify_step_output
from worktree.core.runtime.models import RunContext, RunObserver


def _render_to_text(renderable: Table | Group | Panel, *, width: int = 100) -> str:
    """Helper to render Rich renderables to plain text string."""
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=width)
    console.print(renderable)
    return buffer.getvalue()


class TestLiveStepItemFormatting:
    """Tests for LiveStepItem formatting helpers."""

    def test_format_step_glyph(self) -> None:
        assert "yellow" in _format_step_glyph("running")
        assert "green" in _format_step_glyph("completed")
        assert "red" in _format_step_glyph("failed")
        assert "dim" in _format_step_glyph("pending")

    def test_format_step_elapsed_running(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="lint", status="running", start_time=100.0)
        assert _format_step_elapsed(item, now=102.5) == "2.5s"

    def test_format_step_elapsed_completed(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="lint", status="completed", duration=1.234)
        assert _format_step_elapsed(item, now=200.0) == "1.23s"

    def test_format_step_elapsed_pending(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="lint", status="pending")
        assert _format_step_elapsed(item, now=200.0) == "-"

    def test_resolve_step_duration(self) -> None:
        item = LiveStepItem(idx=1, total=1, name="s1", start_time=10.0)
        result = make_ok_result(duration_seconds=5.0)
        assert _resolve_step_duration(item, result, now=14.5) == pytest.approx(4.5)

        item_no_start = LiveStepItem(idx=1, total=1, name="s1")
        assert _resolve_step_duration(item_no_start, result, now=20.0) == 5.0

    def test_format_failure_detail(self) -> None:
        result_with_msg = make_failed_result(error_message="Boom", stderr="detail trace")
        assert "Boom\ndetail trace" == _format_failure_detail(result_with_msg)

        result_already_contains = make_failed_result(error_message="Boom detail trace", stderr="detail trace")
        assert "Boom detail trace" == _format_failure_detail(result_already_contains)

        result_without_msg = make_failed_result(error_message=None, exit_code=2, stderr="err")
        assert "Command failed with exit code 2.\nerr" == _format_failure_detail(result_without_msg)

        result_empty_streams = make_failed_result(error_message="Fail", stdout="", stderr="")
        assert "Fail" == _format_failure_detail(result_empty_streams)


class TestLiveRenderers:
    """Tests for table, panel, and composite renderable builders."""

    def test_build_live_step_table_empty(self) -> None:
        table = build_live_step_table([])
        rendered = _render_to_text(table)
        assert "Task Execution Progress" in rendered
        assert "Status" in rendered
        assert "Step" in rendered

    def test_build_live_step_table_with_sandbox(self) -> None:
        table = build_live_step_table([], sandbox_info="In-place")
        rendered = _render_to_text(table)
        assert "Task Execution Progress (In-place)" in rendered

    def test_build_live_step_table_with_steps(self) -> None:
        steps = [
            LiveStepItem(
                idx=1,
                total=2,
                name="lint",
                command="ruff check .",
                status="completed",
                duration=0.42,
            ),
            LiveStepItem(
                idx=2,
                total=2,
                name="test",
                command="pytest -q",
                status="running",
                start_time=10.0,
            ),
        ]
        table = build_live_step_table(steps, now=11.8)
        rendered = _render_to_text(table)
        assert "[1/2] lint" in rendered
        assert "ruff check ." in rendered
        assert "0.42s" in rendered
        assert "[2/2] test" in rendered
        assert "pytest -q" in rendered
        assert "1.8s" in rendered

    def test_build_live_output_panel_empty(self) -> None:
        panel = build_live_output_panel("test_step", [])
        assert isinstance(panel, Panel)
        rendered = _render_to_text(panel)
        assert "Output: test_step" in rendered

    def test_build_live_output_panel_with_lines(self) -> None:
        lines = [
            "tests/cli/test_status.py ..",
            "tests/core/test_step.py .....",
            "tests/core/test_runtime.py ...",
        ]
        panel = build_live_output_panel("test", lines)
        rendered = _render_to_text(panel)
        assert "Output: test" in rendered
        assert "tests/cli/test_status.py .." in rendered
        assert "tests/core/test_runtime.py ..." in rendered

    def test_build_live_renderable_without_active_step(self) -> None:
        steps = [LiveStepItem(idx=1, total=1, name="build", status="completed", duration=1.0)]
        renderable = build_live_renderable(steps, active_step_name=None)
        assert isinstance(renderable, Table)
        rendered = _render_to_text(renderable)
        assert "Task Execution Progress" in rendered
        assert "Output:" not in rendered

    def test_build_live_renderable_with_active_step(self) -> None:
        steps = [
            LiveStepItem(idx=1, total=2, name="lint", status="completed", duration=0.5),
            LiveStepItem(idx=2, total=2, name="test", status="running", start_time=10.0),
        ]
        lines = ["running pytest...", "2 passed"]
        renderable = build_live_renderable(
            steps,
            active_step_name="test",
            output_lines=lines,
            sandbox_info="In-place",
            now=12.0,
        )
        assert isinstance(renderable, Group)
        rendered = _render_to_text(renderable)
        assert "Task Execution Progress (In-place)" in rendered
        assert "[1/2] lint" in rendered
        assert "[2/2] test" in rendered
        assert "Output: test" in rendered
        assert "running pytest..." in rendered
        assert "2 passed" in rendered


class TestLiveRunObserver:
    """Tests for LiveRunObserver lifecycle, ring buffer truncation, and step transitions."""

    def test_init_defaults(self) -> None:
        output, _ = make_rich_output()
        observer = LiveRunObserver(output)
        assert observer.output is output
        assert observer.output_buffer_size == DEFAULT_OUTPUT_BUFFER_SIZE
        assert observer._active_step_name is None
        assert isinstance(observer._active_output, deque)
        assert observer._active_output.maxlen == 8

    def test_custom_output_buffer_size(self) -> None:
        observer = LiveRunObserver(output_buffer_size=4)
        assert observer.output_buffer_size == 4
        assert observer._active_output.maxlen == 4

    def test_sandbox_ready_active_and_inplace(self) -> None:
        output, buf = make_rich_output()
        observer = LiveRunObserver(output)

        observer.on_sandbox_ready(Path("/tmp/sbx_1"), active=True)
        assert observer.sandbox_info == "Active (/tmp/sbx_1)"
        output.print()
        assert "Sandbox: Active (/tmp/sbx_1)" in buf.getvalue()

        observer.on_sandbox_ready(Path("/workspace"), active=False)
        assert observer.sandbox_info == "In-place (workspace)"
        output.print()
        assert "Sandbox: In-place (workspace)" in buf.getvalue()

    def test_step_start_resets_output_buffer(self) -> None:
        observer = LiveRunObserver()
        step1 = make_cmd_step(step_id="s1", name="lint", command="ruff check")
        observer.on_step_start(1, 2, step1)

        assert observer._active_step_name == "lint"
        assert len(observer.steps) == 1
        assert observer.steps[0].status == "running"

        observer.on_step_output(1, 2, step1, "line 1\n")
        assert list(observer._active_output) == ["line 1"]

        # Starting step 2 must clear the output buffer
        step2 = make_cmd_step(step_id="s2", name="test", command="pytest")
        observer.on_step_start(2, 2, step2)
        assert observer._active_step_name == "test"
        assert len(observer.steps) == 2
        assert list(observer._active_output) == []

    def test_on_step_output_ring_buffer_truncation(self) -> None:
        observer = LiveRunObserver(output_buffer_size=3)
        step = make_cmd_step(step_id="s1", name="build")
        observer.on_step_start(1, 1, step)

        for i in range(1, 6):
            observer.on_step_output(1, 1, step, f"line {i}\r\n")

        # Capacity is 3, so only lines 3, 4, 5 remain
        assert list(observer._active_output) == ["line 3", "line 4", "line 5"]

    def test_step_done_clears_active_output_and_step_name(self) -> None:
        observer = LiveRunObserver()
        step = make_cmd_step(step_id="s1", name="lint")
        observer.on_step_start(1, 1, step)
        observer.on_step_output(1, 1, step, "All checks passed\n")

        assert observer._active_step_name == "lint"
        assert list(observer._active_output) == ["All checks passed"]

        result = make_ok_result(step_id="s1")
        observer.on_step_done(1, 1, result)

        assert observer._active_step_name is None
        assert list(observer._active_output) == []
        assert observer.steps[0].status == "completed"

    def test_step_done_records_failure(self) -> None:
        observer = LiveRunObserver()
        step = make_cmd_step(step_id="s1", name="test")
        observer.on_step_start(1, 1, step)

        result = make_failed_result(step_id="s1", error_message="Tests failed", exit_code=1)
        observer.on_step_done(1, 1, result)

        assert observer._active_step_name is None
        assert observer.steps[0].status == "failed"
        assert observer.steps[0].error_message is not None
        assert "Tests failed" in observer.steps[0].error_message

    def test_step_done_when_empty_steps(self) -> None:
        observer = LiveRunObserver()
        result = make_ok_result(step_id="s1")
        # Should not raise exception
        observer.on_step_done(1, 1, result)
        assert observer._active_step_name is None

    def test_sandbox_cleanup(self) -> None:
        output, buf = make_rich_output()
        observer = LiveRunObserver(output)

        observer.on_sandbox_cleanup(kept=True, path=Path("/tmp/sbx"))
        output.print()
        assert "Sandbox: Retained (/tmp/sbx)" in buf.getvalue()

        observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx"))
        output.print()
        assert "Sandbox: Cleaned" in buf.getvalue()

    def test_enter_and_exit_context_manager(self) -> None:
        output, _ = make_rich_output()
        observer = LiveRunObserver(output)

        with observer:
            assert observer._live is not None
            step = make_cmd_step(step_id="s1", name="lint")
            observer.on_step_start(1, 1, step)
            observer.on_step_output(1, 1, step, "Checking...")
            assert observer._active_step_name == "lint"

        assert observer._live is None
        assert observer._active_step_name is None
        assert list(observer._active_output) == []


class TestCliRunObserver:
    """Tests for standard non-live CliRunObserver."""

    def test_lifecycle(self) -> None:
        output, buf = make_rich_output()
        observer = CliRunObserver(output)

        with observer:
            observer.on_sandbox_ready(Path("/tmp/sbx"), active=True)
            step = make_cmd_step(step_id="s1", name="lint", command="ruff check .")
            observer.on_step_start(1, 2, step)
            # on_step_output is safe no-op
            observer.on_step_output(1, 2, step, "some output line\n")
            observer.on_step_done(1, 2, make_ok_result(step_id="s1"))

            failed_step = make_cmd_step(step_id="s2", name="test", command="pytest")
            observer.on_step_start(2, 2, failed_step)
            observer.on_step_done(2, 2, make_failed_result(step_id="s2", error_message="failure"))
            observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx"))

        output.print()
        output_text = buf.getvalue()
        assert "Sandbox: Active (/tmp/sbx)" in output_text
        assert "[STEP 1/2] Executing lint..." in output_text
        assert "[STEP 1/2] s1 COMPLETED" in output_text
        assert "[STEP 2/2] Executing test..." in output_text
        assert "[STEP 2/2] s2 FAILED: failure" in output_text
        assert "Sandbox: Cleaned" in output_text


class TestResolveRunObserver:
    """Tests for resolve_run_observer factory."""

    def test_non_interactive_returns_cli_observer(self) -> None:
        output = RichOutput(console=Console(force_terminal=True))
        observer = resolve_run_observer(output, non_interactive=True)
        assert isinstance(observer, CliRunObserver)

    def test_non_terminal_returns_cli_observer(self) -> None:
        output = RichOutput(console=Console(force_terminal=False))
        observer = resolve_run_observer(output, non_interactive=False)
        assert isinstance(observer, CliRunObserver)

    def test_terminal_returns_live_observer(self) -> None:
        output = RichOutput(console=Console(force_terminal=True))
        observer = resolve_run_observer(output, non_interactive=False, output_buffer_size=12)
        assert isinstance(observer, LiveRunObserver)
        assert observer.output_buffer_size == 12


class TestProtocolAndEngineIntegration:
    """Tests protocol compliance and engine helper."""

    def test_run_observer_protocol_compliance(self) -> None:
        live_obs = LiveRunObserver()
        cli_obs = CliRunObserver()
        assert isinstance(live_obs, RunObserver)
        assert isinstance(cli_obs, RunObserver)

    def test_notify_step_output_invokes_observer(self) -> None:
        observer = MagicMock(spec=RunObserver)
        context = RunContext(steps=[], cwd=Path.cwd(), observer=observer)
        step = make_cmd_step(step_id="s1")

        _notify_step_output(context, 1, 1, step, "test line", stream="stdout")
        observer.on_step_output.assert_called_once_with(1, 1, step, "test line", stream="stdout")
