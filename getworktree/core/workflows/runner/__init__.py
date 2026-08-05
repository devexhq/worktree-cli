"""Iteration controller: sandbox → trigger → agent → patch until stop.

Package layout:
- ``runner_models`` (sibling module): run-result models and callback type
  aliases (``WorkflowFinalStatus``, ``StopReason``, ``AttemptRecord``,
  ``StepOutcome``, ``WorkflowRunResult``, ``*Fn`` aliases).
- ``helpers``: stateless utility functions shared by the step functions.
- ``steps``: ``_WorkflowContext`` plus the ``_run_*_step`` functions for each
  stage of an attempt (trigger, agent, approval, patch).
- ``runner``: ``run_workflow_iteration``, the top-level orchestrator.

This ``__init__`` re-exports the full public API so existing imports of
``getworktree.core.workflows.runner`` keep working unchanged.
"""

from __future__ import annotations

from getworktree.core.workflows.runner.helpers import (
    default_list_changed_files,
    resolve_max_attempts,
)
from getworktree.core.workflows.runner.runner import run_workflow_iteration
from getworktree.core.workflows.runner_models import (
    ApplyPatchFn,
    ApprovePatchFn,
    AttemptRecord,
    BuildPayloadFn,
    CleanupSandboxFn,
    CreateSandboxFn,
    DiscardMutationFn,
    IsAbortedFn,
    ListChangedFilesFn,
    OnAttemptEndFn,
    OnEventFn,
    RunTriggerFn,
    StepOutcome,
    StopReason,
    WorkflowFinalStatus,
    WorkflowRunResult,
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
    "OnAttemptEndFn",
    "OnEventFn",
    "RunTriggerFn",
    "StepOutcome",
    "StopReason",
    "WorkflowFinalStatus",
    "WorkflowRunResult",
    "default_list_changed_files",
    "resolve_max_attempts",
    "run_workflow_iteration",
]
