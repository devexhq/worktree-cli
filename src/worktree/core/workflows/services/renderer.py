"""Pure text formatters for workflow run error panel bodies."""

from __future__ import annotations

from worktree.common.models import DefinitionResolutionResult
from worktree.core.catalog.models import DefinitionValidationOutcome
from worktree.core.db import CatalogRecord


def format_workflow_run_resolve_failure(result: DefinitionResolutionResult[CatalogRecord]) -> str:
    """Return plain failure body text for a resolve failure.

    Args:
        result: Non-ok ``DefinitionResolutionResult``.

    Returns:
        Joined resolve errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Failed to resolve workflow."


def format_workflow_run_validate_failure(result: DefinitionValidationOutcome) -> str:
    """Return plain failure body text for a validation failure.

    Args:
        result: Non-ok ``DefinitionValidationOutcome``.

    Returns:
        Joined validation errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Workflow definition is invalid."
