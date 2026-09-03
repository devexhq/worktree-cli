"""Event ComponentFormatters decomposed into single-class modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.events import (
    ErrorPanelEvent,
    LockWaitEvent,
    LoopLifecycleEvent,
    MessageEvent,
    RunSuccessEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
    WarningEvent,
)
from worktree.cli.ui.formatters.common import DispatcherProtocol

from .error_panel import ErrorPanelFormatter
from .lock_wait import LockWaitFormatter
from .loop import LoopLifecycleFormatter
from .message import MessageFormatter
from .run_success import RunSuccessFormatter
from .sandbox import SandboxLifecycleFormatter
from .step_done import StepDoneFormatter
from .step_output import StepOutputFormatter
from .step_start import StepStartFormatter
from .warning import WarningFormatter


def register_event_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all UI event formatters on the provided dispatcher."""
    dispatcher.register(ErrorPanelEvent, ErrorPanelFormatter())
    dispatcher.register(LockWaitEvent, LockWaitFormatter())
    dispatcher.register(WarningEvent, WarningFormatter())
    dispatcher.register(MessageEvent, MessageFormatter())
    dispatcher.register(RunSuccessEvent, RunSuccessFormatter())
    dispatcher.register(StepStartEvent, StepStartFormatter())
    dispatcher.register(StepDoneEvent, StepDoneFormatter())
    dispatcher.register(StepOutputEvent, StepOutputFormatter())
    dispatcher.register(SandboxLifecycleEvent, SandboxLifecycleFormatter())
    dispatcher.register(LoopLifecycleEvent, LoopLifecycleFormatter())


__all__ = [
    "ErrorPanelFormatter",
    "LockWaitFormatter",
    "LoopLifecycleFormatter",
    "MessageFormatter",
    "RunSuccessFormatter",
    "SandboxLifecycleFormatter",
    "StepDoneFormatter",
    "StepOutputFormatter",
    "StepStartFormatter",
    "WarningFormatter",
    "register_event_formatters",
]
