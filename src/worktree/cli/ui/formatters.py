"""ComponentFormatters for runtime UI event DTOs."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.events import (
    ErrorPanelEvent,
    LoopLifecycleEvent,
    MessageEvent,
    RunSuccessEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
    WarningEvent,
)
from worktree.common.types import ComponentFormatter


class ErrorPanelFormatter(ComponentFormatter[ErrorPanelEvent]):
    """Formatter for error panels."""

    def to_rich(self, data: ErrorPanelEvent) -> Panel:
        """Render error panel with border and title."""
        return Panel(data.message, title=data.title, border_style=data.border_style)

    def to_json_serializable(self, data: ErrorPanelEvent) -> dict[str, Any]:
        """Convert ErrorPanelEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class WarningFormatter(ComponentFormatter[WarningEvent]):
    """Formatter for warning notices."""

    def to_rich(self, data: WarningEvent) -> Text:
        """Render warning notice in yellow."""
        return Text.from_markup(f"[yellow]Warning:[/] {data.message}")

    def to_json_serializable(self, data: WarningEvent) -> dict[str, Any]:
        """Convert WarningEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class MessageFormatter(ComponentFormatter[MessageEvent]):
    """Formatter for generic message lines."""

    def to_rich(self, data: MessageEvent) -> Text:
        """Render formatted or styled message text."""
        if data.style is not None:
            return Text(data.message, style=data.style)
        return Text.from_markup(data.message)

    def to_json_serializable(self, data: MessageEvent) -> dict[str, Any]:
        """Convert MessageEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class RunSuccessFormatter(ComponentFormatter[RunSuccessEvent]):
    """Formatter for blueprint run completion summaries."""

    def to_rich(self, data: RunSuccessEvent) -> Text:
        """Render green success summary line."""
        kind_str = data.kind.value.capitalize()
        return Text.from_markup(
            f"[bold green]{kind_str} Run Completed:[/] {data.blueprint_name} "
            f"(session: {data.session_id}, status: {data.status.value})"
        )

    def to_json_serializable(self, data: RunSuccessEvent) -> dict[str, Any]:
        """Convert RunSuccessEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class StepStartFormatter(ComponentFormatter[StepStartEvent]):
    """Formatter for step start notices."""

    def to_rich(self, data: StepStartEvent) -> Text:
        """Render step start progress line."""
        step_label = data.name or data.step_id
        cmd_info = f" (command: {data.command})" if data.command else ""
        return Text.from_markup(f"[STEP {data.idx}/{data.total}] Executing {step_label}{cmd_info}...")

    def to_json_serializable(self, data: StepStartEvent) -> dict[str, Any]:
        """Convert StepStartEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class StepDoneFormatter(ComponentFormatter[StepDoneEvent]):
    """Formatter for step completion and failure notices."""

    def to_rich(self, data: StepDoneEvent) -> Text:
        """Render step completed or failed line."""
        step_label = data.step_id
        if data.ok:
            return Text.from_markup(f"[bold green][STEP {data.idx}/{data.total}] {step_label} COMPLETED[/]")
        msg = data.error_message or f"exit code {data.exit_code}"
        return Text.from_markup(f"[bold red][STEP {data.idx}/{data.total}] {step_label} FAILED[/]: {msg}")

    def to_json_serializable(self, data: StepDoneEvent) -> dict[str, Any]:
        """Convert StepDoneEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class StepOutputFormatter(ComponentFormatter[StepOutputEvent]):
    """Formatter for live step output lines."""

    def to_rich(self, data: StepOutputEvent) -> Text:
        """Render raw output text."""
        return Text(data.line)

    def to_json_serializable(self, data: StepOutputEvent) -> dict[str, Any]:
        """Convert StepOutputEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class SandboxLifecycleFormatter(ComponentFormatter[SandboxLifecycleEvent]):
    """Formatter for sandbox lifecycle notices."""

    def to_rich(self, data: SandboxLifecycleEvent) -> Text:
        """Render sandbox ready or cleanup notice."""
        if data.action == "ready":
            if data.active:
                return Text(f"Sandbox: Active ({data.path})")
            return Text("Sandbox: In-place (workspace)")
        if data.action == "cleanup":
            if data.kept:
                return Text(f"Sandbox: Retained ({data.path})")
            return Text("Sandbox: Cleaned")
        return Text(f"Sandbox: {data.action} ({data.path})")

    def to_json_serializable(self, data: SandboxLifecycleEvent) -> dict[str, Any]:
        """Convert SandboxLifecycleEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


class LoopLifecycleFormatter(ComponentFormatter[LoopLifecycleEvent]):
    """Formatter for loop execution notices."""

    def to_rich(self, data: LoopLifecycleEvent) -> Text:
        """Render loop progress, turn, evaluation, or termination line."""
        if data.action == "start":
            return Text(f"[{data.loop_id}] Starting loop block (max_iterations: {data.max_iterations})")
        if data.action == "turn_start":
            return Text(f"[{data.loop_id}] --- Iteration Turn {data.turn}/{data.max_iterations} ---")
        if data.action == "conditions_evaluated":
            return Text(data.message or f"[{data.loop_id}] Evaluated 'until' conditions")
        if data.action == "done":
            if data.status == "completed":
                return Text(f"[{data.loop_id}] Loop completed successfully in {data.turn} iteration(s).")
            return Text(f"[{data.loop_id}] Loop terminated with status '{data.status}' after {data.turn} iteration(s).")
        return Text(data.message or f"[{data.loop_id}] {data.action}")

    def to_json_serializable(self, data: LoopLifecycleEvent) -> dict[str, Any]:
        """Convert LoopLifecycleEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")


def register_ui_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all UI event ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(ErrorPanelEvent, ErrorPanelFormatter())
    target.register(WarningEvent, WarningFormatter())
    target.register(MessageEvent, MessageFormatter())
    target.register(RunSuccessEvent, RunSuccessFormatter())
    target.register(StepStartEvent, StepStartFormatter())
    target.register(StepDoneEvent, StepDoneFormatter())
    target.register(StepOutputEvent, StepOutputFormatter())
    target.register(SandboxLifecycleEvent, SandboxLifecycleFormatter())
    target.register(LoopLifecycleEvent, LoopLifecycleFormatter())


# Auto-register UI formatters on the central ui_dispatcher
register_ui_formatters()
