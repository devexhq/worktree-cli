"""Execution metadata builder and environment variable formatting service."""

from __future__ import annotations

import json
from collections.abc import Sequence

from worktree.core.step.models import (
    ExecutionIdentity,
    ExecutionMetadata,
    PreviousStepMetadata,
    StepDefinition,
    StepMetadata,
    StepResult,
    TaskMetadata,
    WorkflowMetadata,
)


def build_execution_metadata(
    step: StepDefinition,
    *,
    step_index: int = 1,
    attempt: int = 1,
    identity: ExecutionIdentity | None = None,
    previous_step: PreviousStepMetadata | None = None,
    steps: Sequence[PreviousStepMetadata] | None = None,
) -> ExecutionMetadata:
    """Build structured execution metadata for a single step attempt."""
    step_metadata = StepMetadata(
        id=step.id,
        name=step.name or "",
        index=step_index,
        attempt=attempt,
    )
    task_metadata = (
        TaskMetadata(name=identity.task_name, sha=identity.task_sha) if identity is not None else TaskMetadata()
    )
    workflow_metadata = (
        WorkflowMetadata(name=identity.workflow_name, sha=identity.workflow_sha)
        if identity is not None
        else WorkflowMetadata()
    )
    historical_steps = list(steps) if steps is not None else []
    if previous_step is not None:
        prior_metadata = previous_step
    elif historical_steps:
        prior_metadata = historical_steps[-1]
    else:
        prior_metadata = PreviousStepMetadata()

    return ExecutionMetadata(
        step=step_metadata,
        task=task_metadata,
        workflow=workflow_metadata,
        previous_step=prior_metadata,
        steps=historical_steps,
    )


def metadata_to_env(metadata: ExecutionMetadata) -> dict[str, str]:
    """Format full WT_* process environment variable map. All 14 keys always present."""
    return {
        "WT_STEP_ID": metadata.step.id,
        "WT_STEP_NAME": metadata.step.name,
        "WT_STEP_INDEX": str(metadata.step.index),
        "WT_STEP_ATTEMPT": str(metadata.step.attempt),
        "WT_TASK_NAME": metadata.task.name,
        "WT_TASK_SHA": metadata.task.sha,
        "WT_WORKFLOW_NAME": metadata.workflow.name,
        "WT_WORKFLOW_SHA": metadata.workflow.sha,
        "WT_PREVIOUS_STEP_ID": metadata.previous_step.id,
        "WT_PREVIOUS_STEP_NAME": metadata.previous_step.name,
        "WT_PREVIOUS_STEP_INDEX": metadata.previous_step.index,
        "WT_PREVIOUS_STEP_STATUS": metadata.previous_step.status,
        "WT_PREVIOUS_STEP_EXIT_CODE": metadata.previous_step.exit_code,
        "WT_STEPS_JSON": json.dumps([item.model_dump() for item in metadata.steps]),
    }


def previous_step_metadata_from_result(
    result: StepResult,
    *,
    step_index: int,
    step_name: str = "",
) -> PreviousStepMetadata:
    """Construct PreviousStepMetadata from a completed StepResult."""
    return PreviousStepMetadata(
        id=result.step_id,
        name=step_name,
        index=str(step_index),
        status=result.status,
        exit_code=str(result.exit_code),
    )
