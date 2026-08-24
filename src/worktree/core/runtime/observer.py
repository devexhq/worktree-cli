"""Execution observers for step execution (live and stream)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.live import Live
from rich.table import Table

from worktree.common.utils import RichOutput
from worktree.core.runtime.models import RunObserver
from worktree.core.step import StepDefinition, StepResult

if TYPE_CHECKING:
    from types import TracebackType


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


def _format_failure_detail(result: StepResult) -> str:
    err_msg = result.error_message or f"Command failed with exit code {result.exit_code}."
    detail = (result.stderr or result.stdout or "").strip()
    if detail and detail not in err_msg:
        return f"{err_msg}\n{detail}"
    return err_msg


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

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the CLI."""
        step_label = result.step_id
        if result.ok:
            self.output.add_line(f"[bold green][STEP {idx}/{total}] {step_label} COMPLETED[/]")
            return
        msg = result.error_message or result.stderr or f"exit code {result.exit_code}"
        self.output.add_line(f"[bold red][STEP {idx}/{total}] {step_label} FAILED[/]: {msg}")

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention to the CLI."""
        if kept:
            self.output.add_line(f"Sandbox: Retained ({path})")
        else:
            self.output.add_line("Sandbox: Cleaned")


class LiveRunObserver(RunObserver):
    """Observer adapter displaying live execution progress with Rich Live."""

    def __init__(self, output: RichOutput | None = None) -> None:
        self.output = output or RichOutput()
        self.sandbox_info: str | None = None
        self.steps: list[LiveStepItem] = []
        self._live: Live | None = None

    def __enter__(self) -> LiveRunObserver:
        self._live = Live(
            build_live_step_table(self.steps, sandbox_info=self.sandbox_info),
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
            self._live.update(build_live_step_table(self.steps, sandbox_info=self.sandbox_info))
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

    def on_step_done(self, idx: int, total: int, result: StepResult) -> None:
        """Report step completion or failure to the CLI."""
        if not self.steps:
            return
        current = self.steps[-1]
        current.status = "completed" if result.ok else "failed"
        current.duration = _resolve_step_duration(current, result, time.monotonic())
        if not result.ok:
            current.error_message = _format_failure_detail(result)
        self._refresh()

    def on_sandbox_cleanup(self, kept: bool, path: Path) -> None:
        """Report sandbox cleanup or retention to the CLI."""
        if kept:
            self.output.add_line(f"Sandbox: Retained ({path})")
        else:
            self.output.add_line("Sandbox: Cleaned")

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(build_live_step_table(self.steps, sandbox_info=self.sandbox_info))


def resolve_run_observer(
    output: RichOutput,
    *,
    non_interactive: bool = False,
) -> LiveRunObserver | CliRunObserver:
    """Return LiveRunObserver for interactive TTY terminals, else CliRunObserver."""
    if non_interactive or not output.console.is_terminal:
        return CliRunObserver(output)
    return LiveRunObserver(output)
