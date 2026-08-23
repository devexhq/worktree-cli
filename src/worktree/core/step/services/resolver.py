"""Resolve a step's ``uses``/``run`` shorthand into a concrete, executable ``StepDefinition``."""

from pathlib import Path

from worktree.core.step.exceptions import StepValidationError
from worktree.core.step.models import StepDefinition, StepType

from .loader import load_step_by_id


def resolve_step_definition(step: StepDefinition, *, path: Path | None = None) -> StepDefinition:
    """Resolve a step, following its dependencies if any."""
    if step.run is not None:
        return _resolve_run(step)

    if step.uses is not None:
        return _resolve_from_uses(step, path)

    if step.type is not None:
        return step

    raise StepValidationError(f"Could not resolve step: {step.id}")


def _resolve_run(step: StepDefinition) -> StepDefinition:
    return StepDefinition.model_validate(
        {
            "id": step.id,
            "name": step.name,
            "description": step.description,
            "type": StepType.COMMAND,
            "command": step.run,
            "env": step.env,
            "timeout_seconds": step.timeout_seconds,
            "assert": step.assert_,
            "on_failure": step.on_failure,
        }
    )


def _resolve_from_uses(step: StepDefinition, path: Path | None = None) -> StepDefinition:
    """Load the referenced step and apply only the fields the referencing step explicitly set."""
    if path is None:
        raise StepValidationError(f"Cannot resolve 'uses: {step.uses}' without a workspace path.")
    base_step = load_step_by_id(str(step.uses), path)
    fields_set = step.model_fields_set

    def _pick(field_name: str):
        return getattr(step, field_name) if field_name in fields_set else getattr(base_step, field_name)

    return StepDefinition.model_validate(
        {
            "id": step.id,
            "name": _pick("name"),
            "type": base_step.type,
            "description": _pick("description"),
            "command": base_step.command,
            "prompt": _pick("prompt"),
            "script_path": _pick("script_path"),
            "tools": _pick("tools"),
            "env": {**base_step.env, **step.env},
            "timeout_seconds": _pick("timeout_seconds"),
            "assert": _pick("assert_"),
            "on_failure": _pick("on_failure"),
        }
    )
