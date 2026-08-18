"""Unit tests for LiveRunObserver and live task execution renderers."""

from pathlib import Path

from rich.console import Console

from worktree.cli.task.observer import LiveRunObserver
from worktree.cli.task.renderers import (
    LiveStepItem,
    _format_step_elapsed,
    _format_step_glyph,
    build_live_step_table,
)
from worktree.common.utils import RichOutput
from worktree.core.step import StepDefinition, StepResult


def test_format_step_glyph() -> None:
    assert "yellow" in _format_step_glyph("running")
    assert "green" in _format_step_glyph("completed")
    assert "red" in _format_step_glyph("failed")
    assert "dim" in _format_step_glyph("pending")


def test_format_step_elapsed() -> None:
    item_running = LiveStepItem(
        idx=1,
        total=2,
        name="step1",
        status="running",
        start_time=100.0,
    )
    assert _format_step_elapsed(item_running, 102.5) == "2.5s"

    item_done = LiveStepItem(
        idx=1,
        total=2,
        name="step1",
        status="completed",
        duration=1.234,
    )
    assert _format_step_elapsed(item_done, 105.0) == "1.23s"

    item_pending = LiveStepItem(idx=2, total=2, name="step2", status="pending")
    assert _format_step_elapsed(item_pending, 105.0) == "-"


def test_build_live_step_table() -> None:
    steps = [
        LiveStepItem(
            idx=1,
            total=2,
            name="lint",
            command="ruff check .",
            status="completed",
            duration=0.5,
        ),
        LiveStepItem(
            idx=2,
            total=2,
            name="test",
            command="pytest",
            status="running",
            start_time=100.0,
        ),
    ]
    table = build_live_step_table(steps, sandbox_info="Active (/tmp/sbx)", now=102.0)
    assert table.title == "Task Execution Progress (Active (/tmp/sbx))"
    assert len(table.columns) == 4
    assert len(table.rows) == 2


def test_live_run_observer_lifecycle() -> None:
    console = Console(record=True, width=120)
    output = RichOutput(console=console)
    observer = LiveRunObserver(output)

    with observer:
        observer.on_sandbox_ready(Path("/tmp/sandbox_1"), active=True)
        assert observer.sandbox_info == "Active (/tmp/sandbox_1)"

        step1 = StepDefinition(id="step-1", name="lint", run="ruff check .")
        observer.on_step_start(1, 2, step1)
        assert len(observer.steps) == 1
        assert observer.steps[0].status == "running"

        result1 = StepResult(
            step_id="step-1",
            status="completed",
            exit_code=0,
            stdout="all good",
            stderr="",
            duration_seconds=0.15,
        )
        observer.on_step_done(1, 2, result1)
        assert observer.steps[0].status == "completed"

        step2 = StepDefinition(id="step-2", name="test", run="pytest")
        observer.on_step_start(2, 2, step2)
        assert len(observer.steps) == 2
        assert observer.steps[1].status == "running"

        result2 = StepResult(
            step_id="step-2",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="test failed",
            error_message="1 test failed",
            duration_seconds=0.45,
        )
        observer.on_step_done(2, 2, result2)
        assert observer.steps[1].status == "failed"
        assert observer.steps[1].error_message == "1 test failed"

        observer.on_sandbox_cleanup(kept=True, path=Path("/tmp/sandbox_1"))

    assert observer._live is None


def test_live_run_observer_in_place_and_cleaned() -> None:
    console = Console(record=True, width=120)
    output = RichOutput(console=console)
    observer = LiveRunObserver(output)

    observer.on_sandbox_ready(Path("/tmp/repo"), active=False)
    assert observer.sandbox_info == "In-place (workspace)"

    observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/repo"))
    assert "Sandbox: Cleaned" in console.export_text()


def test_live_run_observer_formats_stderr_details() -> None:
    output = RichOutput()
    observer = LiveRunObserver(output)

    step = StepDefinition(id="run-tests", name="run-tests", run="pytest")
    observer.on_step_start(1, 1, step)

    result = StepResult(
        step_id="run-tests",
        status="failed",
        exit_code=127,
        stdout="",
        stderr="sh: 1: pytest: not found",
        error_message="Command failed with exit code 127.",
        duration_seconds=0.05,
    )
    observer.on_step_done(1, 1, result)

    assert observer.steps[0].error_message is not None
    assert "Command failed with exit code 127." in observer.steps[0].error_message
    assert "sh: 1: pytest: not found" in observer.steps[0].error_message
