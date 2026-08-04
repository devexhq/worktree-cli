"""Iteration controller: sandbox → trigger → agent → patch until stop.

Package layout:
- ``runner_models`` (sibling module): run-result models and callback type
  aliases (``LoopFinalStatus``, ``StopReason``, ``AttemptRecord``,
  ``StepOutcome``, ``LoopRunResult``, ``*Fn`` aliases).
- ``helpers``: stateless utility functions shared by the step functions.
- ``steps``: ``_LoopContext`` plus the ``_run_*_step`` functions for each
  stage of an attempt (trigger, agent, approval, patch).
- ``runner``: ``run_loop_iteration``, the top-level orchestrator.

This ``__init__`` re-exports the full public API so existing imports of
``getworktree.core.loops.runner`` keep working unchanged.
"""

from __future__ import annotations

from getworktree.core.loops.runner.helpers import (
    default_list_changed_files,
    resolve_max_attempts,
)
from getworktree.core.loops.runner.runner import run_loop_iteration
from getworktree.core.loops.runner_models import (
    ApplyPatchFn,
    ApprovePatchFn,
    AttemptRecord,
    BuildPayloadFn,
    CleanupSandboxFn,
    CreateSandboxFn,
    DiscardMutationFn,
    IsAbortedFn,
    ListChangedFilesFn,
    LoopFinalStatus,
    LoopRunResult,
    OnAttemptEndFn,
    OnEventFn,
    RunTriggerFn,
    StepOutcome,
    StopReason,
)

__all__ = [
    "ApplyPatchFn",
    "ApprovePatchFn",
    "AttemptRecord",
    "BuildPayloadFn",
    "CleanupSandboxFn",
    "CreateSandboxFn",
    "DiscardMutationFn",
    "IsAbortedFn",
    "ListChangedFilesFn",
    "LoopFinalStatus",
    "LoopRunResult",
    "OnAttemptEndFn",
    "OnEventFn",
    "RunTriggerFn",
    "StepOutcome",
    "StopReason",
    "default_list_changed_files",
    "resolve_max_attempts",
    "run_loop_iteration",
]
