"""Unit tests for getworktree.common.exceptions module."""

from __future__ import annotations

from getworktree.common.exceptions import (
    DefinitionError,
    DefinitionLoadError,
    DefinitionNotFoundError,
    DefinitionValidationError,
)
from getworktree.core.step.exceptions import StepNotFoundError, StepValidationError
from getworktree.core.workflows.exceptions import (
    WorkflowLoadError,
    WorkflowValidationError,
)


def test_definition_error_hierarchy() -> None:
    assert issubclass(DefinitionNotFoundError, DefinitionError)
    assert issubclass(DefinitionLoadError, DefinitionError)
    assert issubclass(DefinitionValidationError, DefinitionError)


def test_step_exceptions_subclass_shared_generics() -> None:
    assert issubclass(StepNotFoundError, DefinitionNotFoundError)
    assert issubclass(StepValidationError, DefinitionValidationError)


def test_workflow_exceptions_subclass_shared_generics() -> None:
    assert issubclass(WorkflowLoadError, DefinitionLoadError)
    assert issubclass(WorkflowValidationError, DefinitionValidationError)


def test_workflow_error_umbrella_removed() -> None:
    import getworktree.core.workflows.exceptions as workflow_exceptions

    assert not hasattr(workflow_exceptions, "WorkflowError")


def test_workflow_error_not_exported_from_package() -> None:
    import getworktree.core.workflows as workflows

    assert "WorkflowError" not in workflows.__all__
    assert not hasattr(workflows, "WorkflowError")
