from pathlib import Path

from getworktree.common.models import FailurePolicy, FailureSpec
from getworktree.core.step import DEFAULT_STEP_TIMEOUT_SECONDS, StepAssert, StepDefinition, StepType, StepValidationError

from .loader import load_step_by_id

_DEFAULT_FAILURE = FailureSpec(action=FailurePolicy.ABORT)


def resolve_step_definition(step: StepDefinition, *, cwd: Path | None = None) -> StepDefinition:
    """Resolve a step, following its dependencies if any."""
    if step.run is not None:
        return _resolve_run(step)

    if step.uses is not None:
        return _resolve_from_uses(step, cwd)

    if step.type is not None:
        return step

    raise StepValidationError(f"Could not resolve step: {step.id}")


def _resolve_run(step: StepDefinition) -> StepDefinition:
    return StepDefinition(
        id=step.id,
        name=step.name,
        description=step.description,
        type=StepType.COMMAND,
        command=step.run,
        env=step.env,
        timeout_seconds=step.timeout_seconds,
        assert_=step.assert_,
        on_failure=step.on_failure,
    )


def _resolve_from_uses(step: StepDefinition, cwd: Path | None = None) -> StepDefinition:
    base_step = load_step_by_id(str(step.uses), cwd)
    return StepDefinition(
        id=step.id,
        name=step.name or base_step.name,
        type=base_step.type,
        description=step.description or base_step.description,
        command=base_step.command,
        prompt=step.prompt or base_step.prompt,
        script_path=step.script_path or base_step.script_path,
        tools=step.tools or base_step.tools,
        env={**base_step.env, **step.env},
        timeout_seconds=step.timeout_seconds if step.timeout_seconds != DEFAULT_STEP_TIMEOUT_SECONDS else base_step.timeout_seconds,  # Only take `step` if different from "DEFAULT_VALUE"
        assert_=_merge_assert(base_step.assert_, step.assert_),
        on_failure=_merge_on_failure(base_step.on_failure, step.on_failure)
    )


def _merge_assert(base_value: StepAssert | None, step_value: StepAssert | None) -> StepAssert | None:
    return step_value if step_value is not None else base_value


def _merge_on_failure(base_value: FailureSpec, step_value: FailureSpec) -> FailureSpec:
    if step_value != _DEFAULT_FAILURE:
        return step_value
    return base_value
