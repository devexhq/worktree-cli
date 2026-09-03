"""CLI RunObserver implementations routing execution lifecycle events to UiDispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.cli.ui.events import (
    LoopLifecycleEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
)
from worktree.common.utils import RichOutput
from worktree.core.runtime.models import RunObserver
from worktree.core.runtime.observer import LiveRunObserver
from worktree.core.step import ConditionEvaluationResult, StepDefinition, StepResult

if TYPE_CHECKING:
    from types import TracebackType


class DispatcherRunObserver(RunObserver):
    """Observer adapter converting runtime lifecycle callbacks into UI events for UiDispatcher."""

    def __init__(self, dispatcher: UiDispatcher) -> None:
        """Initialize observer with a target UiDispatcher instance.

        Args:
            dispatcher: UiDispatcher instance to route events through.
        """
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
    """Return LiveRunObserver for interactive terminal sessions, else DispatcherRunObserver.

    Args:
        dispatcher: The active UiDispatcher instance.
        non_interactive: Whether non-interactive execution is requested.
        output_format: Output format ('terminal' or 'json').

    Returns:
        A RunObserver instance suitable for the execution context.
    """
    if output_format == "json" or non_interactive or not dispatcher._console.is_terminal:
        return DispatcherRunObserver(dispatcher)
    return LiveRunObserver(output=RichOutput(dispatcher._console))
