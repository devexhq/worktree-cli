"""Unit tests for WorkflowDefinition defaults.on_failure fill-if-omitted."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worktree.core.step import FailurePolicy, LoopStepBlock, StepDefinition
from worktree.core.workflows.models import WORKFLOW_VALIDATOR, WorkflowDefinition


def _base_workflow(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "version": "1.0",
        "name": "feature-dev",
        "id": "feature-dev",
        "steps": [{"id": "unit", "run": "pytest"}],
    }
    data.update(overrides)
    return data


def test_workflow_defaults_omitted_keeps_step_abort() -> None:
    workflow = WorkflowDefinition.model_validate(_base_workflow())
    assert workflow.defaults.on_failure is None
    assert isinstance(workflow.steps, list)
    step = workflow.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.on_failure.action == FailurePolicy.ABORT


def test_workflow_defaults_on_failure_inherited_when_step_omits() -> None:
    workflow = WorkflowDefinition.model_validate(_base_workflow(defaults={"on_failure": "continue"}))
    assert workflow.defaults.on_failure is not None
    assert workflow.defaults.on_failure.action == FailurePolicy.CONTINUE
    assert isinstance(workflow.steps, list)
    step = workflow.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.on_failure.action == FailurePolicy.CONTINUE


def test_workflow_defaults_on_failure_object_form_inherited() -> None:
    workflow = WorkflowDefinition.model_validate(
        _base_workflow(
            defaults={
                "on_failure": {
                    "action": "retry",
                    "max_retries": 4,
                    "backoff_ms": 100,
                    "on_max_retries": "continue",
                }
            }
        )
    )
    assert isinstance(workflow.steps, list)
    step = workflow.steps[0]
    assert isinstance(step, StepDefinition)
    assert step.on_failure.action == FailurePolicy.RETRY
    assert step.on_failure.max_retries == 4
    assert step.on_failure.backoff_ms == 100
    assert step.on_failure.on_max_retries == FailurePolicy.CONTINUE


def test_workflow_explicit_step_on_failure_wins_unchanged() -> None:
    workflow = WorkflowDefinition.model_validate(
        _base_workflow(
            defaults={"on_failure": "continue"},
            steps=[
                {"id": "unit", "run": "pytest"},
                {"id": "publish", "run": "./publish.sh", "on_failure": "abort"},
            ],
        )
    )
    assert isinstance(workflow.steps, list)
    first, second = workflow.steps
    assert isinstance(first, StepDefinition)
    assert isinstance(second, StepDefinition)
    assert first.on_failure.action == FailurePolicy.CONTINUE
    assert second.on_failure.action == FailurePolicy.ABORT


def test_workflow_defaults_do_not_fill_loop_block_itself() -> None:
    workflow = WorkflowDefinition.model_validate(
        _base_workflow(
            defaults={"on_failure": "continue"},
            steps=[
                {
                    "id": "dev-cycle",
                    "type": "loop",
                    "until": ["steps.unit.exit_code == 0"],
                    "do": [{"id": "unit", "run": "pytest"}],
                }
            ],
        )
    )
    assert isinstance(workflow.steps, list)
    loop = workflow.steps[0]
    assert isinstance(loop, LoopStepBlock)
    # Nested do[] fill is intentionally out of scope for this change.
    assert loop.do[0].on_failure.action == FailurePolicy.ABORT


def test_workflow_defaults_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate(_base_workflow(defaults={"on_failure": "abort", "extra": True}))


def test_workflow_schema_accepts_defaults_on_failure() -> None:
    result = WORKFLOW_VALIDATOR.validate(_base_workflow(defaults={"on_failure": {"action": "retry", "max_retries": 2}}))
    assert result.ok
    assert result.errors == []


def test_workflow_schema_rejects_unknown_defaults_keys() -> None:
    result = WORKFLOW_VALIDATOR.validate(_base_workflow(defaults={"unknown": True}))
    assert not result.ok


def test_workflow_schema_rejects_invalid_defaults_on_failure() -> None:
    result = WORKFLOW_VALIDATOR.validate(_base_workflow(defaults={"on_failure": "nope"}))
    assert not result.ok
