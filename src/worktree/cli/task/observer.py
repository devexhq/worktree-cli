"""Live Rich execution observer for task execution."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.live import Live

from worktree.common.utils import RichOutput
from worktree.core.runtime import RunObserver
from worktree.core.step import StepDefinition, StepResult

from .renderers import LiveStepItem, build_live_step_table

if TYPE_CHECKING:
    from types import TracebackType


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
            self.output.info(f"Sandbox: Active ({path})")
        else:
            self.sandbox_info = "In-place (workspace)"
            self.output.info("Sandbox: In-place (workspace)")
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
            self.output.info(f"Sandbox: Retained ({path})")
        else:
            self.output.info("Sandbox: Cleaned")

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(build_live_step_table(self.steps, sandbox_info=self.sandbox_info))
