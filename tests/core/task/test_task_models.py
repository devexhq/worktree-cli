"""Unit tests for TaskDefinition model and step shorthand normalization."""

from getworktree.core.step import StepType
from getworktree.core.task.models import TaskDefinition


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
