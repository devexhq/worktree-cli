"""Execution observers for step execution (live and stream)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from worktree.common.utils import RichOutput
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
    """Build the Rich table displaying dynamic step execution progress.

    Args:
        steps: List of LiveStepItem instances.
        sandbox_info: Optional string describing sandbox state.
        now: Optional monotonic timestamp for testing.

    Returns:
        A Rich Table displaying step execution status, names, commands, and elapsed time.
    """
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
    """Build a framed Rich Panel displaying buffered live step output lines.

    Args:
        step_name: The display name or label of the active step.
        lines: Sequence of recently captured output lines.

    Returns:
        A Rich Panel with title "Output: <step_name>".
    """
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
    """Build the composite Rich renderable with step progress table and optional output panel.

    Args:
        steps: List of LiveStepItem instances.
        active_step_name: Optional name of the currently running step.
        output_lines: Optional buffered lines for the active step.
        sandbox_info: Optional string describing sandbox state.
        now: Optional monotonic timestamp for testing.

    Returns:
        A Rich Group containing the table and output panel when an active step is running,
        or just the Table otherwise.
    """
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
    """Observer adapter forwarding runtime step lifecycle events to RichOutput line-by-line."""

    def __init__(self, output: RichOutput | None = None) -> None:
        self.output = output or RichOutput()

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
        """Report sandbox readiness to the CLI."""
        if active:
            self.output.add_line(f"Sandbox: Active ({path})")
        else:
            self.output.add_line("Sandbox: In-place (workspace)")

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Report step start progress to the CLI."""
        step_label = step.name or step.id
        cmd_info = f" (command: {step.run})" if step.run else ""
        self.output.add_line(f"[STEP {idx}/{total}] Executing {step_label}{cmd_info}...")

    def on_step_output(
        self,
        idx: int,
        total: int,
        step: StepDefinition,
        line: str,
        stream: str = "stdout",
    ) -> None:
        """Handle live output emitted by a running step (no-op for non-live CLI output)."""
        pass

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the CLI."""
        step_label = result.step_id
        if result.ok:
            self.output.add_line(f"[bold green][STEP {idx}/{total}] {step_label} COMPLETED[/]")
            return
        msg = result.error_message or result.stderr or f"exit code {result.exit_code}"
        self.output.add_line(f"[bold red][STEP {idx}/{total}] {step_label} FAILED[/]: {msg}")

    def on_loop_start(self, loop_id: str, max_iterations: int) -> None:
        """Report loop start progress to the CLI."""
        self.output.add_line(f"\\[{loop_id}] Starting loop block (max_iterations: {max_iterations})")

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        """Report turn start progress to the CLI."""
        self.output.add_line(f"\\[{loop_id}] --- Iteration Turn {turn}/{max_iterations} ---")

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        """Report evaluated until conditions to the CLI."""
        self.output.add_line(f"\\[{loop_id}] Evaluated 'until' conditions:")
        for r in results:
            self.output.add_line(f"  - {r.expression}: {r.detail}")
        if not all_passed and next_turn is not None:
            self.output.add_line(f"\\[{loop_id}] Conditions not met. Continuing to turn {next_turn}...")

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        """Report loop completion to the CLI."""
        if status == "completed":
            self.output.add_line(f"\\[{loop_id}] Loop completed successfully in {turns} iteration(s).")
        else:
            self.output.add_line(f"\\[{loop_id}] Loop terminated with status '{status}' after {turns} iteration(s).")

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention to the CLI."""
        if kept:
            self.output.add_line(f"Sandbox: Retained ({path})")
        else:
            self.output.add_line("Sandbox: Cleaned")


class LiveRunObserver(RunObserver):
    """Observer adapter displaying live execution progress and output tail with Rich Live."""

    def __init__(
        self,
        output: RichOutput | None = None,
        *,
        output_buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE,
    ) -> None:
        self.output = output or RichOutput()
        self.sandbox_info: str | None = None
        self.steps: list[LiveStepItem] = []
        self.output_buffer_size = output_buffer_size
        self._active_step_name: str | None = None
        self._active_output: deque[str] = deque(maxlen=output_buffer_size)
        self._live: Live | None = None

    def __enter__(self) -> LiveRunObserver:
        self._live = Live(
            self._build_renderable(),
            console=self.output.console,
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
        """Report sandbox readiness to the CLI."""
        if active:
            self.sandbox_info = f"Active ({path})"
            self.output.add_line(f"Sandbox: Active ({path})")
        else:
            self.sandbox_info = "In-place (workspace)"
            self.output.add_line("Sandbox: In-place (workspace)")
        self._refresh()

    def on_step_start(self, idx: int, total: int, step: StepDefinition) -> None:
        """Report step start progress to the CLI."""
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
        """Handle live output emitted by the running step."""
        step_label = step.name or step.id
        self._active_step_name = step_label
        self._active_output.append(line.rstrip("\r\n"))
        self._refresh()

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the CLI."""
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
        """Report loop start progress to the CLI."""
        self.output.add_line(f"\\[{loop_id}] Starting loop block (max_iterations: {max_iterations})")
        self._refresh()

    def on_loop_turn_start(self, loop_id: str, turn: int, max_iterations: int) -> None:
        """Report turn start progress to the CLI."""
        self.output.add_line(f"\\[{loop_id}] --- Iteration Turn {turn}/{max_iterations} ---")
        self._refresh()

    def on_loop_conditions_evaluated(
        self,
        loop_id: str,
        results: list[ConditionEvaluationResult],
        all_passed: bool,
        next_turn: int | None = None,
    ) -> None:
        """Report evaluated until conditions to the CLI."""
        self.output.add_line(f"\\[{loop_id}] Evaluated 'until' conditions:")
        for r in results:
            self.output.add_line(f"  - {r.expression}: {r.detail}")
        if not all_passed and next_turn is not None:
            self.output.add_line(f"\\[{loop_id}] Conditions not met. Continuing to turn {next_turn}...")
        self._refresh()

    def on_loop_done(self, loop_id: str, status: str, turns: int) -> None:
        """Report loop completion to the CLI."""
        if status == "completed":
            self.output.add_line(f"\\[{loop_id}] Loop completed successfully in {turns} iteration(s).")
        else:
            self.output.add_line(f"\\[{loop_id}] Loop terminated with status '{status}' after {turns} iteration(s).")
        self._refresh()

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention to the CLI."""
        if kept:
            self.output.add_line(f"Sandbox: Retained ({path})")
        else:
            self.output.add_line("Sandbox: Cleaned")

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


def resolve_run_observer(
    output: RichOutput,
    *,
    non_interactive: bool = False,
    output_buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE,
) -> LiveRunObserver | CliRunObserver:
    """Return LiveRunObserver for interactive TTY terminals, else CliRunObserver."""
    if non_interactive or not output.console.is_terminal:
        return CliRunObserver(output)
    return LiveRunObserver(output, output_buffer_size=output_buffer_size)
