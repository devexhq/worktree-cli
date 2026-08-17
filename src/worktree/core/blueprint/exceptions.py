"""Exceptions for blueprint definition models."""

from __future__ import annotations

from worktree.common.exceptions import DefinitionLoadError, DefinitionValidationError


class BlueprintLoadError(DefinitionLoadError):
    """Raised when blueprint YAML syntax is invalid or unreadable."""


class BlueprintValidationError(DefinitionValidationError):
    """Raised when blueprint model validation fails."""
