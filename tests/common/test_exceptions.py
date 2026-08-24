"""Unit tests for worktree.common.exceptions module."""

from __future__ import annotations

from worktree.common.exceptions import (
    DefinitionError,
    DefinitionLoadError,
    DefinitionNotFoundError,
    DefinitionValidationError,
)
from worktree.core.step.exceptions import StepNotFoundError, StepValidationError
from worktree.core.workflows.exceptions import (
    WorkflowLoadError,
    WorkflowValidationError,
)


class CommonExceptionsTests:
    """Unit tests for exception hierarchies and deprecations."""

    def test_definition_error_hierarchy(self) -> None:
        assert issubclass(DefinitionNotFoundError, DefinitionError)
        assert issubclass(DefinitionLoadError, DefinitionError)
        assert issubclass(DefinitionValidationError, DefinitionError)

    def test_step_exceptions_subclass_shared_generics(self) -> None:
        assert issubclass(StepNotFoundError, DefinitionNotFoundError)
        assert issubclass(StepValidationError, DefinitionValidationError)

    def test_workflow_exceptions_subclass_shared_generics(self) -> None:
        assert issubclass(WorkflowLoadError, DefinitionLoadError)
        assert issubclass(WorkflowValidationError, DefinitionValidationError)

    def test_workflow_error_umbrella_removed(self) -> None:
        import worktree.core.workflows.exceptions as workflow_exceptions

        assert not hasattr(workflow_exceptions, "WorkflowError")

    def test_workflow_error_not_exported_from_package(self) -> None:
        import worktree.core.workflows as workflows

        assert "WorkflowError" not in workflows.__all__
        assert not hasattr(workflows, "WorkflowError")
