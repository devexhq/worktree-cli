"""UI domain module for formatted CLI rendering and event dispatching."""

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
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
    WelcomeBannerEvent,
)

__all__ = [
    "ErrorPanelEvent",
    "LockWaitEvent",
    "LoopLifecycleEvent",
    "MessageEvent",
    "RunSuccessEvent",
    "SandboxLifecycleEvent",
    "StepDoneEvent",
    "StepOutputEvent",
    "StepStartEvent",
    "UiDispatcher",
    "WarningEvent",
    "WelcomeBannerEvent",
    "ui_dispatcher",
]
