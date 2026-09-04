"""Tests for live interactive display manager and renderable builders in cli/ui/live.py."""

from __future__ import annotations

import io

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from worktree.cli.ui.events import SandboxLifecycleEvent, StepDoneEvent, StepOutputEvent, StepStartEvent
from worktree.cli.ui.live import (
    LiveDisplayManager,
    LiveStepItem,
    _format_failure_detail,
    _format_step_elapsed,
    _format_step_glyph,
    _resolve_step_duration,
    build_live_output_panel,
    build_live_renderable,
    build_live_step_table,
)


def _render_to_text(renderable: Table | Group | Panel, *, width: int = 100) -> str:
    """Helper to render Rich renderables to plain text string."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=width)
    console.print(renderable)
    return buffer.getvalue()


class TestLiveStepItemFormatting:
    """Tests for LiveStepItem formatting helpers."""

    def test_format_step_glyph(self) -> None:
        assert _format_step_glyph("running") == "[bold yellow]•[/bold yellow]"
        assert _format_step_glyph("completed") == "[bold green]✔[/bold green]"
        assert _format_step_glyph("failed") == "[bold red]✖[/bold red]"
        assert _format_step_glyph("pending") == "[dim]○[/dim]"
        assert _format_step_glyph("unknown") == "[dim]○[/dim]"

    def test_format_step_elapsed_running(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="step-1", command="echo 1", status="running", start_time=100.0)
        assert _format_step_elapsed(item, 103.5) == "3.5s"

    def test_format_step_elapsed_completed(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="step-1", command="echo 1", status="completed", duration=1.234)
        assert _format_step_elapsed(item, 110.0) == "1.23s"

    def test_format_step_elapsed_pending(self) -> None:
        item = LiveStepItem(idx=1, total=2, name="step-1", command="echo 1", status="pending")
        assert _format_step_elapsed(item, 100.0) == "-"

    def test_resolve_step_duration(self) -> None:
        item_with_start = LiveStepItem(idx=1, total=1, name="s1", command=None, start_time=10.0)
        assert _resolve_step_duration(item_with_start, 5.0, 14.5) == 4.5

        item_without_start = LiveStepItem(idx=1, total=1, name="s1", command=None, start_time=None)
        assert _resolve_step_duration(item_without_start, 2.5, 100.0) == 2.5

    def test_format_failure_detail(self) -> None:
        event_with_msg = StepDoneEvent(
            idx=1,
            total=1,
            step_id="s1",
            ok=False,
            exit_code=1,
            error_message="Custom failure message",
        )
        assert _format_failure_detail(event_with_msg) == "Custom failure message"

        event_without_msg = StepDoneEvent(
            idx=1,
            total=1,
            step_id="s1",
            ok=False,
            exit_code=2,
            error_message=None,
        )
        assert _format_failure_detail(event_without_msg) == "Command failed with exit code 2."


class TestLiveRenderers:
    """Tests for table and panel renderable builders."""

    def test_build_live_step_table_empty(self) -> None:
        table = build_live_step_table([])
        rendered = _render_to_text(table)
        assert "Task Execution Progress" in rendered
        assert "Status" in rendered

    def test_build_live_step_table_with_sandbox(self) -> None:
        table = build_live_step_table([], sandbox_info="Active (/tmp/sbx)")
        assert table.title == "Task Execution Progress (Active (/tmp/sbx))"
        rendered = _render_to_text(table)
        assert "Active" in rendered

    def test_build_live_step_table_with_steps(self) -> None:
        steps = [
            LiveStepItem(idx=1, total=2, name="build", command="cargo build", status="completed", duration=2.1),
            LiveStepItem(idx=2, total=2, name="test", command="cargo test", status="running", start_time=10.0),
        ]
        table = build_live_step_table(steps, now=12.5)
        rendered = _render_to_text(table)
        assert "[1/2] build" in rendered
        assert "cargo build" in rendered
        assert "2.10s" in rendered
        assert "[2/2] test" in rendered
        assert "2.5s" in rendered

    def test_build_live_output_panel_empty(self) -> None:
        panel = build_live_output_panel("lint", [])
        rendered = _render_to_text(panel)
        assert "Output: lint" in rendered

    def test_build_live_output_panel_with_lines(self) -> None:
        panel = build_live_output_panel("test", ["Running tests...", "2 passed"])
        rendered = _render_to_text(panel)
        assert "Output: test" in rendered
        assert "Running tests..." in rendered
        assert "2 passed" in rendered

    def test_build_live_renderable_without_active_step(self) -> None:
        renderable = build_live_renderable([])
        assert isinstance(renderable, Table)

    def test_build_live_renderable_with_active_step(self) -> None:
        renderable = build_live_renderable([], active_step_name="lint", output_lines=["line 1"])
        assert isinstance(renderable, Group)
        rendered = _render_to_text(renderable)
        assert "Output: lint" in rendered
        assert "line 1" in rendered


class TestLiveDisplayManager:
    """Tests for LiveDisplayManager lifecycle and event routing."""

    def test_init_and_properties(self) -> None:
        console = Console(file=io.StringIO(), force_terminal=True)
        manager = LiveDisplayManager(console, output_buffer_size=4)
        assert manager.console is console
        assert manager.output_buffer_size == 4
        assert not manager.is_active
        assert manager.sandbox_info is None
        assert manager.steps == []

    def test_start_and_stop(self) -> None:
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        manager = LiveDisplayManager(console)

        manager.start()
        assert manager.is_active

        # Calling start again is idempotent
        manager.start()
        assert manager.is_active

        manager.stop()
        assert not manager.is_active

        # Calling stop again is idempotent
        manager.stop()
        assert not manager.is_active

    def test_handle_step_lifecycle(self) -> None:
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        manager = LiveDisplayManager(console, output_buffer_size=3)

        manager.start()
        try:
            # Start step 1
            manager.handle_step_start(StepStartEvent(idx=1, total=2, step_id="s1", name="lint", command="ruff check"))
            assert len(manager.steps) == 1
            assert manager.steps[0].status == "running"
            assert manager._active_step_name == "lint"

            # Buffer step output (more lines than capacity 3)
            for i in range(1, 6):
                manager.handle_step_output(StepOutputEvent(step_id="s1", line=f"line {i}\n"))
            assert list(manager._active_output) == ["line 3", "line 4", "line 5"]

            # Complete step 1
            manager.handle_step_done(
                StepDoneEvent(idx=1, total=2, step_id="s1", ok=True, exit_code=0, duration_seconds=1.5)
            )
            assert manager.steps[0].status == "completed"
            assert manager._active_step_name is None
            assert list(manager._active_output) == []

            # Start and fail step 2
            manager.handle_step_start(StepStartEvent(idx=2, total=2, step_id="s2", name="test", command="pytest"))
            manager.handle_step_done(
                StepDoneEvent(
                    idx=2,
                    total=2,
                    step_id="s2",
                    ok=False,
                    exit_code=1,
                    error_message="Test failure",
                )
            )
            assert manager.steps[1].status == "failed"
            assert manager.steps[1].error_message == "Test failure"
        finally:
            manager.stop()

    def test_handle_sandbox_and_print_above(self) -> None:
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        manager = LiveDisplayManager(console)

        manager.start()
        try:
            # Active sandbox
            manager.handle_sandbox(
                SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True),
                Text("Sandbox: Active (/tmp/sbx)"),
            )
            assert manager.sandbox_info == "Active (/tmp/sbx)"

            # Print notice above
            manager.print_above(Text("[loop-1] Starting loop block"))
        finally:
            manager.stop()

        output = buf.getvalue()
        assert "Sandbox: Active (/tmp/sbx)" in output
        assert "[loop-1] Starting loop block" in output

    def test_print_above_when_not_active(self) -> None:
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        manager = LiveDisplayManager(console)
        manager.print_above(Text("Printed directly to console"))
        assert "Printed directly to console" in buf.getvalue()

    def test_handle_sandbox_cleanup(self) -> None:
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        manager = LiveDisplayManager(console)

        manager.handle_sandbox(
            SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=True),
            Text("Sandbox: Retained (/tmp/sbx)"),
        )
        assert "Sandbox: Retained (/tmp/sbx)" in buf.getvalue()
