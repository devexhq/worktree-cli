"""UI domain module for formatted CLI rendering and event dispatching."""

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
from worktree.cli.ui.formatters import (
    ErrorPanelFormatter,
    LoopLifecycleFormatter,
    MessageFormatter,
    RunSuccessFormatter,
    SandboxLifecycleFormatter,
    StepDoneFormatter,
    StepOutputFormatter,
    StepStartFormatter,
    WarningFormatter,
    register_ui_formatters,
)

__all__ = [
    "ErrorPanelEvent",
    "ErrorPanelFormatter",
    "LoopLifecycleEvent",
    "LoopLifecycleFormatter",
    "MessageEvent",
    "MessageFormatter",
    "RunSuccessEvent",
    "RunSuccessFormatter",
    "SandboxLifecycleEvent",
    "SandboxLifecycleFormatter",
    "StepDoneEvent",
    "StepDoneFormatter",
    "StepOutputEvent",
    "StepOutputFormatter",
    "StepStartEvent",
    "StepStartFormatter",
    "UiDispatcher",
    "WarningEvent",
    "WarningFormatter",
    "register_ui_formatters",
    "ui_dispatcher",
]
