"""Unit tests for worktree.common.exceptions module."""

from __future__ import annotations

from worktree.common.exceptions import (
    DefinitionError,
    DefinitionLoadError,
    DefinitionNotFoundError,
    DefinitionValidationError,
)
from worktree.core.step.exceptions import StepNotFoundError, StepValidationError


class CommonExceptionsTests:
    """Unit tests for exception hierarchies and deprecations."""

    def test_definition_error_hierarchy(self) -> None:
        assert issubclass(DefinitionNotFoundError, DefinitionError)
        assert issubclass(DefinitionLoadError, DefinitionError)
        assert issubclass(DefinitionValidationError, DefinitionError)

    def test_step_exceptions_subclass_shared_generics(self) -> None:
        assert issubclass(StepNotFoundError, DefinitionNotFoundError)
        assert issubclass(StepValidationError, DefinitionValidationError)
