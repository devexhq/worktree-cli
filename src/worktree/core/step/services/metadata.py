"""Execution metadata builder and environment variable formatting service."""

from __future__ import annotations

import json
from collections.abc import Sequence

from worktree.core.step.models import (
    BlueprintMetadata,
    ExecutionIdentity,
    ExecutionMetadata,
    IterationMetadata,
    PreviousStepMetadata,
    StepDefinition,
    StepMetadata,
    StepResult,
)


def build_execution_metadata(
    step: StepDefinition,
    *,
    step_index: int = 1,
    attempt: int = 1,
    iteration_index: int = 1,
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
    blueprint_metadata = (
        BlueprintMetadata(name=identity.blueprint_name, key=identity.blueprint_key)
        if identity is not None
        else BlueprintMetadata()
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
        blueprint=blueprint_metadata,
        previous_step=prior_metadata,
        steps=historical_steps,
        iteration=IterationMetadata(index=iteration_index),
    )


def metadata_to_env(metadata: ExecutionMetadata) -> dict[str, str]:
    """Format full WT_* process environment variable map."""
    return {
        "WT_STEP_ID": metadata.step.id,
        "WT_STEP_NAME": metadata.step.name,
        "WT_STEP_INDEX": str(metadata.step.index),
        "WT_STEP_ATTEMPT": str(metadata.step.attempt),
        "WT_ITERATION_INDEX": str(metadata.iteration.index),
        "WT_BLUEPRINT_NAME": metadata.blueprint.name,
        "WT_BLUEPRINT_SHA": metadata.blueprint.key,
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
