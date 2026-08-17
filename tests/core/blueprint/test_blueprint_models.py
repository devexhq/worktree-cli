"""Unit tests for BlueprintDefinition and BlueprintKind."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from worktree.core.blueprint import (
    BlueprintDefinition,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintValidationError,
)
from worktree.core.step import FailurePolicy, LoopStepBlock, StepDefinition, StepType


def _loop_step(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "retry",
        "type": "loop",
        "until": ["steps.unit.exit_code == 0"],
        "do": [{"id": "unit", "run": "pytest"}],
    }
    payload.update(overrides)
    return payload


def test_package_exports_models_and_exceptions() -> None:
    assert BlueprintKind.TASK == "task"
    assert BlueprintKind.WORKFLOW == "workflow"
    assert issubclass(BlueprintLoadError, Exception)
    assert issubclass(BlueprintValidationError, Exception)


def test_construct_task_with_explicit_kind() -> None:
    blueprint = BlueprintDefinition(kind=BlueprintKind.TASK, name="lint")

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.name == "lint"
    assert blueprint.id == "lint"
    assert blueprint.description == ""
    assert blueprint.summary == ""
    assert blueprint.version == 1
    assert blueprint.use_sandbox is True
    assert blueprint.timeout_seconds is None
    assert blueprint.env == {}
    assert blueprint.inputs == {}
    assert blueprint.defaults.on_failure is None
    assert blueprint.steps == []


def test_model_validate_requires_kind() -> None:
    with pytest.raises(ValidationError):
        BlueprintDefinition.model_validate({"name": "lint"})


def test_from_document_injects_kind_and_ignores_authored_kind() -> None:
    blueprint = BlueprintDefinition.from_document(
        {
            "kind": "workflow",
            "name": "lint",
            "description": "Run lints",
            "summary": "ruff",
            "extra_yaml_key": True,
        },
        kind=BlueprintKind.TASK,
    )

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.description == "Run lints"
    assert blueprint.summary == "ruff"


def test_from_document_workflow_kind_overrides_authored_task() -> None:
    blueprint = BlueprintDefinition.from_document({"kind": "task", "name": "ship"}, kind=BlueprintKind.WORKFLOW)
    assert blueprint.kind is BlueprintKind.WORKFLOW


def test_from_document_non_mapping_raises_validation_error() -> None:
    with pytest.raises(BlueprintValidationError, match="must be a mapping"):
        BlueprintDefinition.from_document(["not", "a", "mapping"], kind=BlueprintKind.TASK)  # type: ignore[arg-type]


def test_from_document_invalid_payload_raises_blueprint_validation_error() -> None:
    with pytest.raises(BlueprintValidationError, match="kind='task'"):
        BlueprintDefinition.from_document({"name": ""}, kind=BlueprintKind.TASK)


def test_none_description_and_summary_coerce_to_empty() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {"kind": "task", "name": "lint", "description": None, "summary": None}
    )
    assert blueprint.description == ""
    assert blueprint.summary == ""


def test_id_defaults_to_name() -> None:
    blueprint = BlueprintDefinition.model_validate({"kind": "workflow", "name": "ship"})
    assert blueprint.id == "ship"


def test_explicit_id_is_preserved() -> None:
    blueprint = BlueprintDefinition.model_validate({"kind": "workflow", "name": "ship", "id": "ship-v1"})
    assert blueprint.id == "ship-v1"


def test_timeout_seconds_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BlueprintDefinition.model_validate({"kind": "task", "name": "lint", "timeout_seconds": 0})


def test_defaults_on_failure_inherited_when_step_omits() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "task",
            "name": "inherit",
            "defaults": {"on_failure": "continue"},
            "steps": [{"id": "unit", "run": "pytest"}],
        }
    )
    assert blueprint.defaults.on_failure is not None
    assert blueprint.defaults.on_failure.action == FailurePolicy.CONTINUE
    assert isinstance(blueprint.steps[0], StepDefinition)
    assert blueprint.steps[0].on_failure.action == FailurePolicy.CONTINUE


def test_invalid_defaults_on_failure_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BlueprintDefinition.model_validate(
            {
                "kind": "task",
                "name": "bad-action",
                "defaults": {"on_failure": "not-a-policy"},
                "steps": [{"id": "unit", "run": "pytest"}],
            }
        )


def test_command_shorthand_maps_to_run_and_fills_id() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {"kind": "task", "name": "pytest-task", "steps": [{"command": "pytest"}]}
    )
    step = blueprint.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.id == "step-1"
    assert step.run == "pytest"
    assert step.command is None
    assert step.type is None


def test_command_shorthand_slugifies_name_for_id() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "workflow",
            "name": "named-steps",
            "steps": [{"name": "Run Unit Tests", "command": "pytest -q"}],
        }
    )
    step = blueprint.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.id == "run-unit-tests"
    assert step.name == "Run Unit Tests"
    assert step.run == "pytest -q"


def test_command_shorthand_not_mapped_when_type_present() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "task",
            "name": "explicit",
            "steps": [{"id": "custom-id", "type": "command", "command": "echo hi"}],
        }
    )
    step = blueprint.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.id == "custom-id"
    assert step.type == StepType.COMMAND
    assert step.command == "echo hi"
    assert step.run is None


def test_anonymous_steps_get_indexed_ids() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "task",
            "name": "multi",
            "steps": [{"command": "echo one"}, {"command": "echo two"}],
        }
    )
    assert [step.id for step in blueprint.steps] == ["step-1", "step-2"]


def test_task_with_loop_step_is_rejected() -> None:
    with pytest.raises(ValidationError, match="kind=task cannot contain loop steps"):
        BlueprintDefinition.model_validate(
            {
                "kind": "task",
                "name": "no-loops",
                "steps": [_loop_step()],
            }
        )


def test_from_document_task_with_loop_raises_blueprint_validation_error() -> None:
    with pytest.raises(BlueprintValidationError, match="kind=task cannot contain loop steps"):
        BlueprintDefinition.from_document(
            {"name": "no-loops", "steps": [_loop_step()]},
            kind=BlueprintKind.TASK,
        )


def test_workflow_allows_mixed_steps_and_loops() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "workflow",
            "name": "ship",
            "steps": [
                {"id": "unit", "run": "pytest"},
                _loop_step(),
            ],
        }
    )
    assert isinstance(blueprint.steps[0], StepDefinition)
    assert isinstance(blueprint.steps[1], LoopStepBlock)
    assert blueprint.steps[1].id == "retry"


def test_loop_missing_id_is_filled() -> None:
    blueprint = BlueprintDefinition.model_validate(
        {
            "kind": "workflow",
            "name": "ship",
            "steps": [_loop_step(id="")],
        }
    )
    assert isinstance(blueprint.steps[0], LoopStepBlock)
    assert blueprint.steps[0].id == "step-1"


def test_models_module_does_not_import_higher_or_twin_domains() -> None:
    import worktree.core.blueprint.models as models_mod

    source = Path(models_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "worktree.core.catalog",
        "worktree.core.engine",
        "worktree.core.task",
        "worktree.core.workflows",
    ):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
