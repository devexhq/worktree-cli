"""Pure text formatters for workflow run error panel bodies."""

from __future__ import annotations

from getworktree.core.workflows.resolve import WorkflowResolveResult
from getworktree.core.workflows.validate import WorkflowValidationResult


def format_workflow_run_resolve_failure(result: WorkflowResolveResult) -> str:
    """Return plain failure body text for a resolve failure.

    Args:
        result: Non-ok ``WorkflowResolveResult``.

    Returns:
        Joined resolve errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Failed to resolve workflow."


def format_workflow_run_validate_failure(result: WorkflowValidationResult) -> str:
    """Return plain failure body text for a validation failure.

    Args:
        result: Non-ok ``WorkflowValidationResult``.

    Returns:
        Joined validation errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Workflow definition is invalid."
