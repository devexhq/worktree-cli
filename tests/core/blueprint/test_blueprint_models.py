"""Unit tests for BlueprintDefinition."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from worktree.common.models import FailurePolicy
from worktree.core.blueprint import (
    Blueprint,
    BlueprintDefinition,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintValidationError,
)
from worktree.core.step import LoopStepBlock, StepDefinition, StepType


def _loop_step(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "retry",
        "type": "loop",
        "until": ["steps.unit.exit_code == 0"],
        "do": [{"id": "unit", "run": "pytest"}],
    }
    payload.update(overrides)
    return payload


class BlueprintModelExportTests:
    """Tests for package exports and module import boundaries."""

    def test_package_exports_models_and_exceptions(self) -> None:
        assert Blueprint.spec is BlueprintDefinition
        assert issubclass(BlueprintNotFoundError, Exception)
        assert issubclass(BlueprintLoadError, Exception)
        assert issubclass(BlueprintValidationError, Exception)

    def test_models_module_does_not_import_higher_or_twin_domains(self) -> None:
        import worktree.core.blueprint.models as models_mod

        source = Path(models_mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("worktree.core.catalog", "worktree.core.engine"):
            assert f"import {forbidden}" not in source
            assert f"from {forbidden}" not in source


class BlueprintModelValidationTests:
    """Tests for BlueprintDefinition validation and coercion."""

    def test_construct_blueprint_uses_current_defaults(self) -> None:
        blueprint = BlueprintDefinition.model_validate({"name": "lint"})

        assert blueprint.model_dump(mode="json") == {
            "name": "lint",
            "description": "",
            "summary": "",
            "version": 1,
            "use_sandbox": True,
            "timeout_seconds": None,
            "env": {},
            "inputs": {},
            "defaults": {"on_failure": None},
            "steps": [],
        }

    def test_from_document_defaults_missing_name_from_key(self) -> None:
        blueprint = BlueprintDefinition.from_document(
            {
                "description": "Run lints",
                "summary": "ruff",
                "extra_yaml_key": True,
            },
            key="wt/lint",
        )

        assert blueprint.name == "wt/lint"
        assert blueprint.description == "Run lints"
        assert blueprint.summary == "ruff"

    def test_from_document_preserves_explicit_name_over_key(self) -> None:
        blueprint = BlueprintDefinition.from_document({"name": "ship"}, key="wt/ship")

        assert blueprint.name == "ship"

    def test_from_document_non_mapping_raises_validation_error(self) -> None:
        with pytest.raises(BlueprintValidationError, match="must be a mapping"):
            BlueprintDefinition.from_document(["not", "a", "mapping"], key="ignored")  # pyright: ignore[reportArgumentType]

    def test_from_document_empty_or_null_name_still_fails(self) -> None:
        with pytest.raises(BlueprintValidationError, match="validation failed"):
            BlueprintDefinition.from_document({"name": ""}, key="fallback-name")

        with pytest.raises(BlueprintValidationError, match="validation failed"):
            BlueprintDefinition.from_document({"name": None}, key="fallback-name")

    def test_none_description_and_summary_coerce_to_empty(self) -> None:
        blueprint = BlueprintDefinition.model_validate({"name": "lint", "description": None, "summary": None})

        assert blueprint.description == ""
        assert blueprint.summary == ""

    def test_timeout_seconds_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BlueprintDefinition.model_validate({"name": "lint", "timeout_seconds": 0})


class BlueprintModelDefaultsAndStepsTests:
    """Tests for default policies, step normalization, and loop step handling."""

    def test_defaults_on_failure_inherited_when_step_omits(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
                "name": "inherit",
                "defaults": {"on_failure": "continue"},
                "steps": [{"id": "unit", "run": "pytest"}],
            }
        )

        assert blueprint.defaults.on_failure is not None
        assert blueprint.defaults.on_failure.action == FailurePolicy.CONTINUE
        assert isinstance(blueprint.steps[0], StepDefinition)
        assert blueprint.steps[0].on_failure.action == FailurePolicy.CONTINUE

    def test_invalid_defaults_on_failure_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BlueprintDefinition.model_validate(
                {
                    "name": "bad-action",
                    "defaults": {"on_failure": "not-a-policy"},
                    "steps": [{"id": "unit", "run": "pytest"}],
                }
            )

    def test_command_shorthand_maps_to_run_and_fills_id(self) -> None:
        blueprint = BlueprintDefinition.model_validate({"name": "pytest-task", "steps": [{"command": "pytest"}]})

        step = blueprint.steps[0]
        assert isinstance(step, StepDefinition)
        assert step.id == "step-1"
        assert step.run == "pytest"
        assert step.command is None
        assert step.type is None

    def test_command_shorthand_slugifies_name_for_id(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
                "name": "named-steps",
                "steps": [{"name": "Run Unit Tests", "command": "pytest -q"}],
            }
        )

        step = blueprint.steps[0]
        assert isinstance(step, StepDefinition)
        assert step.id == "run-unit-tests"
        assert step.name == "Run Unit Tests"
        assert step.run == "pytest -q"

    def test_command_shorthand_not_mapped_when_type_present(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
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

    def test_anonymous_steps_get_indexed_ids(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
                "name": "multi",
                "steps": [{"command": "echo one"}, {"command": "echo two"}],
            }
        )

        assert [step.id for step in blueprint.steps] == ["step-1", "step-2"]

    def test_blueprint_allows_mixed_steps_and_loops(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
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

    def test_loop_missing_id_is_filled(self) -> None:
        blueprint = BlueprintDefinition.model_validate(
            {
                "name": "ship",
                "steps": [_loop_step(id="")],
            }
        )

        assert isinstance(blueprint.steps[0], LoopStepBlock)
        assert blueprint.steps[0].id == "step-1"
