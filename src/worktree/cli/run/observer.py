"""CLI RunObserver implementations routing execution lifecycle events to UiDispatcher and Live progress."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.cli.ui.events import (
    LoopLifecycleEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
)
from worktree.core.runtime.models import RunObserver
from worktree.core.step import ConditionEvaluationResult, StepDefinition, StepResult

if TYPE_CHECKING:
    from types import TracebackType

DEFAULT_OUTPUT_BUFFER_SIZE: int = 8


@dataclass
class LiveStepItem:
    """Tracked live execution step state for Rich Live output."""

    idx: int
    total: int
    name: str
    command: str | None = None
    status: str = "pending"
    start_time: float | None = None
    duration: float | None = None
    error_message: str | None = None


def _format_step_glyph(status: str) -> str:
    if status == "running":
        return "[bold yellow]•[/bold yellow]"
    if status == "completed":
        return "[bold green]✔[/bold green]"
    if status == "failed":
        return "[bold red]✖[/bold red]"
    return "[dim]○[/dim]"


def _format_step_elapsed(item: LiveStepItem, now: float) -> str:
    if item.status == "running" and item.start_time is not None:
        return f"{now - item.start_time:.1f}s"
    if item.duration is not None:
        return f"{item.duration:.2f}s"
    return "-"


def build_live_step_table(
    steps: list[LiveStepItem],
    *,
    sandbox_info: str | None = None,
    now: float | None = None,
) -> Table:
    """Build the Rich table displaying dynamic step execution progress."""
    title = f"Task Execution Progress ({sandbox_info})" if sandbox_info else "Task Execution Progress"
    table = Table(title=title, title_justify="left", show_header=True)
    table.add_column("Status", width=6, justify="center")
    table.add_column("Step")
    table.add_column("Command")
    table.add_column("Elapsed", justify="right")

    current_time = now if now is not None else time.monotonic()
    for item in steps:
        glyph = _format_step_glyph(item.status)
        elapsed = _format_step_elapsed(item, current_time)
        cmd_display = item.command or "[dim]-[/dim]"
        step_label = f"[{item.idx}/{item.total}] {item.name}"
        table.add_row(glyph, step_label, cmd_display, elapsed)

    return table


def build_live_output_panel(
    step_name: str,
    lines: Sequence[str],
) -> Panel:
    """Build a framed Rich Panel displaying buffered live step output lines."""
    body_text = Text.from_ansi("\n".join(lines)) if lines else Text("")
    return Panel(body_text, title=f"Output: {step_name}", title_align="left")


def build_live_renderable(
    steps: list[LiveStepItem],
    *,
    active_step_name: str | None = None,
    output_lines: Sequence[str] | None = None,
    sandbox_info: str | None = None,
    now: float | None = None,
) -> Table | Group:
    """Build the composite Rich renderable with step progress table and optional output panel."""
    table = build_live_step_table(steps, sandbox_info=sandbox_info, now=now)
    if active_step_name is not None:
        panel = build_live_output_panel(active_step_name, output_lines or [])
        return Group(table, Text(""), panel)
    return table


def _format_failure_detail(result: StepResult) -> str:
    error_message = result.error_message or f"Command failed with exit code {result.exit_code}."
    detail = (result.stderr or result.stdout or "").strip()
    if detail and detail not in error_message:
        return f"{error_message}\n{detail}"
    return error_message


def _resolve_step_duration(item: LiveStepItem, result: StepResult, now: float) -> float | None:
    if item.start_time is not None:
        return max(0.0, now - item.start_time)
    return result.duration_seconds


class CliRunObserver(RunObserver):
    """Observer adapter forwarding runtime step lifecycle events line-by-line."""

    def __init__(self, output: Any = None, *, console: Console | None = None) -> None:
        self.output = output
        self.console = console or getattr(output, "console", None) or Console()

    def _write_line(self, line: str) -> None:
        if self.output is not None and hasattr(self.output, "add_line"):
            self.output.add_line(line)
        else:
            self.console.print(line)

    def __enter__(self) -> CliRunObserver:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        """Report sandbox readiness to the console."""
        if active:
            self._write_line(f"Sandbox: Active ({path})")
        else:
            self._write_line("Sandbox: In-place (workspace)")

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Report step execution start to the console."""
        step_label = step.name or step.id
        cmd_info = f" (command: {step.run})" if step.run else ""
        self._write_line(f"[STEP {idx}/{total}] Executing {step_label}{cmd_info}...")

    def on_step_output(
        self,
        idx: int,
        total: int,
        step: StepDefinition,
        line: str,
        stream: str = "stdout",
    ) -> None:
        """Handle step output emission (no-op in line-by-line mode)."""
        pass

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the console."""
        step_label = result.step_id
        if result.ok:
            self._write_line(f"[bold green][STEP {idx}/{total}] {step_label} COMPLETED[/]")
            return
        msg = result.error_message or result.stderr or f"exit code {result.exit_code}"
        self._write_line(f"[bold red][STEP {idx}/{total}] {step_label} FAILED[/]: {msg}")

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        """Report loop execution block start."""
        self._write_line(f"\\[{loop_id}] Starting loop block (max_iterations: {max_iterations})")

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        """Report loop iteration turn start."""
        self._write_line(f"\\[{loop_id}] --- Iteration Turn {turn}/{max_iterations} ---")

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        """Report evaluated until loop conditions."""
        self._write_line(f"\\[{loop_id}] Evaluated 'until' conditions:")
        for r in results:
            self._write_line(f"  - {r.expression}: {r.detail}")
        if not all_passed and next_turn is not None:
            self._write_line(f"\\[{loop_id}] Conditions not met. Continuing to turn {next_turn}...")

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        """Report loop block completion."""
        if status == "completed":
            self._write_line(f"\\[{loop_id}] Loop completed successfully in {turns} iteration(s).")
        else:
            self._write_line(f"\\[{loop_id}] Loop terminated with status '{status}' after {turns} iteration(s).")

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention."""
        if kept:
            self._write_line(f"Sandbox: Retained ({path})")
        else:
            self._write_line("Sandbox: Cleaned")


class LiveRunObserver(RunObserver):
    """Observer adapter displaying live execution progress and output tail with Rich Live."""

    def __init__(
        self,
        output: Any = None,
        *,
        console: Console | None = None,
        output_buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE,
    ) -> None:
        self.output = output
        self.console = console or getattr(output, "console", None) or Console()
        self.sandbox_info: str | None = None
        self.steps: list[LiveStepItem] = []
        self.output_buffer_size = output_buffer_size
        self._active_step_name: str | None = None
        self._active_output: deque[str] = deque(maxlen=output_buffer_size)
        self._live: Live | None = None

    def _write_line(self, line: str) -> None:
        if self.output is not None and hasattr(self.output, "add_line"):
            self.output.add_line(line)

    def __enter__(self) -> LiveRunObserver:
        self._live = Live(
            self._build_renderable(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._live is not None:
            self._active_step_name = None
            self._active_output.clear()
            self._live.update(self._build_renderable())
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        """Report sandbox readiness to the live view."""
        if active:
            self.sandbox_info = f"Active ({path})"
            self._write_line(f"Sandbox: Active ({path})")
        else:
            self.sandbox_info = "In-place (workspace)"
            self._write_line("Sandbox: In-place (workspace)")
        self._refresh()

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Report step execution start to the live view."""
        step_label = step.name or step.id
        now = time.monotonic()
        self._active_step_name = step_label
        self._active_output.clear()
        item = LiveStepItem(
            idx=idx,
            total=total,
            name=step_label,
            command=step.run,
            status="running",
            start_time=now,
        )
        self.steps.append(item)
        self._refresh()

    def on_step_output(
        self,
        idx: int,
        total: int,
        step: StepDefinition,
        line: str,
        stream: str = "stdout",
    ) -> None:
        """Buffer live step output line for the active step panel."""
        step_label = step.name or step.id
        self._active_step_name = step_label
        self._active_output.append(line.rstrip("\r\n"))
        self._refresh()

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the live view."""
        if self.steps:
            current = self.steps[-1]
            current.status = "completed" if result.ok else "failed"
            current.duration = _resolve_step_duration(current, result, time.monotonic())
            if not result.ok:
                current.error_message = _format_failure_detail(result)
        self._active_step_name = None
        self._active_output.clear()
        self._refresh()

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        """Report loop execution start to the live view."""
        self._write_line(f"\\[{loop_id}] Starting loop block (max_iterations: {max_iterations})")
        self._refresh()

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        """Report turn execution start to the live view."""
        self._write_line(f"\\[{loop_id}] --- Iteration Turn {turn}/{max_iterations} ---")
        self._refresh()

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        """Report evaluated conditions to the live view."""
        self._write_line(f"\\[{loop_id}] Evaluated 'until' conditions:")
        for r in results:
            self._write_line(f"  - {r.expression}: {r.detail}")
        if not all_passed and next_turn is not None:
            self._write_line(f"\\[{loop_id}] Conditions not met. Continuing to turn {next_turn}...")
        self._refresh()

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        """Report loop completion to the live view."""
        if status == "completed":
            self._write_line(f"\\[{loop_id}] Loop completed successfully in {turns} iteration(s).")
        else:
            self._write_line(f"\\[{loop_id}] Loop terminated with status '{status}' after {turns} iteration(s).")
        self._refresh()

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup to the live view."""
        if kept:
            self._write_line(f"Sandbox: Retained ({path})")
        else:
            self._write_line("Sandbox: Cleaned")

    def _build_renderable(self) -> Table | Group:
        return build_live_renderable(
            self.steps,
            active_step_name=self._active_step_name,
            output_lines=list(self._active_output),
            sandbox_info=self.sandbox_info,
        )

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._build_renderable())


class DispatcherRunObserver(RunObserver):
    """Observer adapter converting runtime lifecycle callbacks into UI events for UiDispatcher."""

    def __init__(self, dispatcher: UiDispatcher) -> None:
        self._dispatcher = dispatcher

    def __enter__(self) -> DispatcherRunObserver:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    def on_sandbox_ready(self, path: Path, active: bool) -> None:
        """Dispatch sandbox readiness event."""
        self._dispatcher.dispatch(SandboxLifecycleEvent(action="ready", path=str(path), active=active))

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Dispatch step start progress event."""
        self._dispatcher.dispatch(
            StepStartEvent(
                idx=idx,
                total=total,
                step_id=step.id,
                name=step.name,
                command=step.run,
            )
        )

    def on_step_output(
        self,
        idx: int,
        total: int,
        step: StepDefinition,
        line: str,
        stream: str = "stdout",
    ) -> None:
        """Dispatch live step output event."""
        self._dispatcher.dispatch(StepOutputEvent(step_id=step.id, line=line, stream=stream))

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Dispatch step completion or failure event."""
        self._dispatcher.dispatch(
            StepDoneEvent(
                idx=idx,
                total=total,
                step_id=result.step_id,
                ok=result.ok,
                exit_code=result.exit_code,
                duration_seconds=result.duration_seconds,
                error_message=result.error_message,
            )
        )

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        """Dispatch loop start event."""
        self._dispatcher.dispatch(LoopLifecycleEvent(loop_id=loop_id, action="start", max_iterations=max_iterations))

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        """Dispatch loop turn start event."""
        self._dispatcher.dispatch(
            LoopLifecycleEvent(
                loop_id=loop_id,
                action="turn_start",
                turn=turn,
                max_iterations=max_iterations,
            )
        )

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        """Dispatch loop until conditions evaluated event."""
        lines = [f"\\[{loop_id}] Evaluated 'until' conditions:"]
        for r in results:
            lines.append(f"  - {r.expression}: {r.detail}")
        if not all_passed and next_turn is not None:
            lines.append(f"\\[{loop_id}] Conditions not met. Continuing to turn {next_turn}...")
        self._dispatcher.dispatch(
            LoopLifecycleEvent(
                loop_id=loop_id,
                action="conditions_evaluated",
                message="\n".join(lines),
            )
        )

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        """Dispatch loop completion event."""
        self._dispatcher.dispatch(
            LoopLifecycleEvent(
                loop_id=loop_id,
                action="done",
                turn=turns,
                status=status,
            )
        )

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Dispatch sandbox cleanup event."""
        self._dispatcher.dispatch(SandboxLifecycleEvent(action="cleanup", path=str(path), kept=kept))


def resolve_cli_observer(
    dispatcher: UiDispatcher,
    *,
    non_interactive: bool = False,
    output_format: str = "terminal",
) -> DispatcherRunObserver | LiveRunObserver:
    """Return LiveRunObserver for interactive terminal sessions, else DispatcherRunObserver."""
    if output_format == "json" or non_interactive or not dispatcher._console.is_terminal:
        return DispatcherRunObserver(dispatcher)
    return LiveRunObserver(console=dispatcher._console)


def resolve_run_observer(
    output: Any,
    *,
    non_interactive: bool = False,
    output_buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE,
) -> LiveRunObserver | CliRunObserver:
    """Return LiveRunObserver for interactive TTY terminals, else CliRunObserver."""
    console = getattr(output, "console", None)
    is_terminal = getattr(console, "is_terminal", False)
    if non_interactive or not is_terminal:
        return CliRunObserver(output=output)
    return LiveRunObserver(output=output, console=console, output_buffer_size=output_buffer_size)
