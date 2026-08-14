"""Tests for pure workflow run error body formatters."""

from __future__ import annotations

from getworktree.common.models import DefinitionResolutionResult, DefinitionResolutionStatus
from getworktree.core.catalog.models import DefinitionValidationOutcome
from getworktree.core.workflows.services.renderer import (
    format_workflow_run_resolve_failure,
    format_workflow_run_validate_failure,
)


class FormatWorkflowRunFailureTests:
    """Failure body formatters used by workflow run error panels."""

    def test_resolve_failure_joins_errors(self) -> None:
        result = DefinitionResolutionResult(
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name="missing",
            errors=["err-a", "err-b"],
        )
        assert format_workflow_run_resolve_failure(result) == "err-a\n\nerr-b"

    def test_resolve_failure_fallback(self) -> None:
        result = DefinitionResolutionResult(
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name="missing",
            errors=[],
        )
        assert format_workflow_run_resolve_failure(result) == "Failed to resolve workflow."

    def test_validate_failure_joins_errors(self) -> None:
        result = DefinitionValidationOutcome(
            status=DefinitionResolutionStatus.LOAD_ERROR,
            errors=["schema bad", "more"],
        )
        assert format_workflow_run_validate_failure(result) == "schema bad\n\nmore"

    def test_validate_failure_fallback(self) -> None:
        result = DefinitionValidationOutcome(
            status=DefinitionResolutionStatus.LOAD_ERROR,
            errors=[],
        )
        assert format_workflow_run_validate_failure(result) == "Workflow definition is invalid."
