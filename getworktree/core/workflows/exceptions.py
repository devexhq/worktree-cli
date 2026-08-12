"""Exceptions for workflow definitions, loading, and validation."""

from __future__ import annotations

from getworktree.common.exceptions import DefinitionLoadError, DefinitionValidationError


class WorkflowLoadError(DefinitionLoadError):
    """Raised when workflow YAML syntax is invalid or cannot be parsed/loaded."""


class WorkflowValidationError(DefinitionValidationError):
    """Raised when workflow schema or model validation fails."""
