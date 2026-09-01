"""Shared step-run engine and sandbox lifecycle for task/workflow execution."""

from worktree.core.runtime.engine import run_steps
from worktree.core.runtime.exceptions import PromptUserInterruptedError
from worktree.core.runtime.failure import USER_CONTINUED_MARKER, effective_terminal_policy
from worktree.core.runtime.loop_runner import LoopBlockRunner
from worktree.core.runtime.models import (
    FailurePromptDecision,
    FailurePrompter,
    LoopPromptDecision,
    RunCheckpoint,
    RunContext,
    RunObserver,
    RunOutcome,
    RunPauseStore,
    StepLoopState,
    parse_checkpoint,
)
from worktree.core.runtime.observer import (
    DEFAULT_OUTPUT_BUFFER_SIZE,
    CliRunObserver,
    LiveRunObserver,
    LiveStepItem,
    build_live_output_panel,
    build_live_renderable,
    build_live_step_table,
    resolve_run_observer,
)
from worktree.core.runtime.prompter import CliFailurePrompter
from worktree.core.step import (
    ExecutionIdentity,
    ExecutionMetadata,
    PreviousStepMetadata,
    StepMetadata,
    TaskMetadata,
    WorkflowMetadata,
)
from worktree.core.step.services.metadata import (
    build_execution_metadata,
    metadata_to_env,
    previous_step_metadata_from_result,
)

__all__ = [
    "DEFAULT_OUTPUT_BUFFER_SIZE",
    "USER_CONTINUED_MARKER",
    "CliFailurePrompter",
    "CliRunObserver",
    "ExecutionIdentity",
    "ExecutionMetadata",
    "FailurePromptDecision",
    "FailurePrompter",
    "LiveRunObserver",
    "LiveStepItem",
    "LoopBlockRunner",
    "LoopPromptDecision",
    "PreviousStepMetadata",
    "PromptUserInterruptedError",
    "RunCheckpoint",
    "RunContext",
    "RunObserver",
    "RunOutcome",
    "RunPauseStore",
    "StepLoopState",
    "StepMetadata",
    "TaskMetadata",
    "WorkflowMetadata",
    "build_execution_metadata",
    "build_live_output_panel",
    "build_live_renderable",
    "build_live_step_table",
    "effective_terminal_policy",
    "metadata_to_env",
    "parse_checkpoint",
    "previous_step_metadata_from_result",
    "resolve_run_observer",
    "run_steps",
]
