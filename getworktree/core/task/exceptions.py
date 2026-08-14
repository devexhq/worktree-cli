"""Exceptions for task definitions, loading, and validation."""

from __future__ import annotations

from getworktree.common.exceptions import DefinitionLoadError, DefinitionValidationError


class TaskLoadError(DefinitionLoadError):
    """Raised when task definition YAML syntax is invalid or unreadable."""


class TaskValidationError(DefinitionValidationError):
    """Raised when task schema or model validation fails."""
