"""Exceptions for workflow definitions, loading, and validation."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base class for workflow errors."""


class WorkflowLoadError(WorkflowError):
    """Raised when workflow YAML syntax is invalid or cannot be parsed/loaded."""


class WorkflowValidationError(WorkflowError):
    """Raised when workflow schema or model validation fails."""
