"""Exceptions for blueprint definition models."""

from __future__ import annotations

from worktree.common.exceptions import (
    DefinitionLoadError,
    DefinitionNotFoundError,
    DefinitionValidationError,
)


class BlueprintNotFoundError(DefinitionNotFoundError):
    """Raised when a blueprint name/SHA is not in the task/workflow catalog."""


class BlueprintLoadError(DefinitionLoadError):
    """Raised when blueprint YAML syntax is invalid or unreadable."""


class BlueprintValidationError(DefinitionValidationError):
    """Raised when blueprint model validation fails."""
