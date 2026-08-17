"""Unit tests for TaskDefinition model and step shorthand normalization."""

import pytest
from pydantic import ValidationError

from worktree.core.step import FailurePolicy, StepType
from worktree.core.task.models import TaskDefinition


def test_task_definition_parses_full_fields() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "run-lints",
            "description": "Lint the project",
            "summary": "Ruff check",
            "use_sandbox": False,
            "steps": [
                {"id": "lint", "type": "command", "command": "ruff check ."},
            ],
        }
    )

    assert task.name == "run-lints"
    assert task.description == "Lint the project"
    assert task.summary == "Ruff check"
    assert task.use_sandbox is False
    assert len(task.steps) == 1
    assert task.steps[0].id == "lint"
    assert task.steps[0].type == StepType.COMMAND
    assert task.steps[0].command == "ruff check ."


def test_task_definition_defaults_use_sandbox_true() -> None:
    task = TaskDefinition.model_validate({"name": "minimal"})
    assert task.use_sandbox is True
    assert task.description == ""
    assert task.summary == ""
    assert task.steps == []
    assert task.defaults.on_failure is None


def test_task_defaults_on_failure_omitted_keeps_step_abort() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "no-defaults",
            "steps": [{"id": "unit", "run": "pytest"}],
        }
    )
    assert task.steps[0].on_failure.action == FailurePolicy.ABORT


def test_task_defaults_on_failure_inherited_when_step_omits() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "inherit",
            "defaults": {"on_failure": "continue"},
            "steps": [{"id": "unit", "run": "pytest"}],
        }
    )
    assert task.defaults.on_failure is not None
    assert task.defaults.on_failure.action == FailurePolicy.CONTINUE
    assert task.steps[0].on_failure.action == FailurePolicy.CONTINUE


def test_task_defaults_on_failure_object_form_inherited() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "retry-default",
            "defaults": {
                "on_failure": {
                    "action": "retry",
                    "max_retries": 5,
                    "backoff_ms": 200,
                    "on_max_retries": "prompt_user",
                }
            },
            "steps": [{"id": "unit", "run": "pytest"}],
        }
    )
    step_failure = task.steps[0].on_failure
    assert step_failure.action == FailurePolicy.RETRY
    assert step_failure.max_retries == 5
    assert step_failure.backoff_ms == 200
    assert step_failure.on_max_retries == FailurePolicy.PROMPT_USER


def test_task_explicit_step_on_failure_wins_unchanged() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "explicit-wins",
            "defaults": {"on_failure": "continue"},
            "steps": [
                {"id": "unit", "run": "pytest"},
                {"id": "publish", "run": "./publish.sh", "on_failure": "abort"},
            ],
        }
    )
    assert task.steps[0].on_failure.action == FailurePolicy.CONTINUE
    assert task.steps[1].on_failure.action == FailurePolicy.ABORT


def test_task_defaults_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        TaskDefinition.model_validate(
            {
                "name": "bad-defaults",
                "defaults": {"on_failure": "abort", "unknown": True},
                "steps": [{"id": "unit", "run": "pytest"}],
            }
        )


def test_task_defaults_on_failure_invalid_action_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskDefinition.model_validate(
            {
                "name": "bad-action",
                "defaults": {"on_failure": "not-a-policy"},
                "steps": [{"id": "unit", "run": "pytest"}],
            }
        )


def test_task_defaults_on_failure_invalid_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskDefinition.model_validate(
            {
                "name": "bad-bounds",
                "defaults": {"on_failure": {"action": "retry", "max_retries": 0}},
                "steps": [{"id": "unit", "run": "pytest"}],
            }
        )


def test_fill_step_shorthand_command_maps_to_run() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "pytest-task",
            "steps": [{"command": "pytest"}],
        }
    )

    assert len(task.steps) == 1
    step = task.steps[0]
    assert step.id == "step-1"
    assert step.run == "pytest"
    assert step.command is None
    assert step.type is None


def test_fill_step_shorthand_slugifies_name_for_id() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "named-steps",
            "steps": [{"name": "Run Unit Tests", "command": "pytest -q"}],
        }
    )

    assert len(task.steps) == 1
    step = task.steps[0]
    assert step.id == "run-unit-tests"
    assert step.name == "Run Unit Tests"
    assert step.run == "pytest -q"


def test_fill_step_shorthand_preserves_explicit_id_and_type() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "explicit",
            "steps": [
                {
                    "id": "custom-id",
                    "type": "command",
                    "command": "echo hi",
                }
            ],
        }
    )

    step = task.steps[0]
    assert step.id == "custom-id"
    assert step.type == StepType.COMMAND
    assert step.command == "echo hi"
    assert step.run is None


def test_fill_step_shorthand_indexes_multiple_anonymous_steps() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "multi",
            "steps": [
                {"command": "echo one"},
                {"command": "echo two"},
            ],
        }
    )

    assert [step.id for step in task.steps] == ["step-1", "step-2"]
    assert [step.run for step in task.steps] == ["echo one", "echo two"]


def test_task_definition_parses_inputs() -> None:
    task = TaskDefinition.model_validate(
        {
            "name": "commit",
            "inputs": {
                "message": {
                    "type": "string",
                    "required": True,
                    "aliases": ["-m", "--message"],
                    "description": "Commit message",
                },
                "allow_empty": {
                    "type": "boolean",
                    "default": False,
                    "aliases": ["--allow-empty"],
                },
            },
            "steps": [{"id": "c", "type": "command", "command": "git commit -m '${{ inputs.message }}'"}],
        }
    )

    assert "message" in task.inputs
    assert task.inputs["message"].required is True
    assert task.inputs["message"].aliases == ["-m", "--message"]
    assert task.inputs["allow_empty"].default is False
