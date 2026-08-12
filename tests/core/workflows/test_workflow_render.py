"""Tests for pure workflow run error body formatters."""

from __future__ import annotations

from getworktree.core.workflows.render import (
    format_workflow_run_resolve_failure,
    format_workflow_run_validate_failure,
)
from getworktree.core.workflows.resolve import (
    WorkflowResolveResult,
    WorkflowResolveStatus,
)
from getworktree.core.workflows.validate import (
    WorkflowValidationResult,
    WorkflowValidationStatus,
)
from tests.helpers import FileSystem


class FormatWorkflowRunFailureTests:
    """Failure body formatters used by workflow run error panels."""

    def test_resolve_failure_joins_errors(self, fs: FileSystem) -> None:
        result = WorkflowResolveResult(
            status=WorkflowResolveStatus.NOT_FOUND,
            name="missing",
            workflows_dir=fs.base_path,
            errors=["err-a", "err-b"],
        )
        assert format_workflow_run_resolve_failure(result) == "err-a\n\nerr-b"

    def test_resolve_failure_fallback(self, fs: FileSystem) -> None:
        result = WorkflowResolveResult(
            status=WorkflowResolveStatus.NOT_FOUND,
            name="missing",
            workflows_dir=fs.base_path,
            errors=[],
        )
        assert format_workflow_run_resolve_failure(result) == "Failed to resolve workflow."

    def test_validate_failure_joins_errors(self, fs: FileSystem) -> None:
        result = WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=fs.base_path / "x.yml",
            errors=["schema bad", "more"],
        )
        assert format_workflow_run_validate_failure(result) == "schema bad\n\nmore"

    def test_validate_failure_fallback(self, fs: FileSystem) -> None:
        result = WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=fs.base_path / "x.yml",
            errors=[],
        )
        assert format_workflow_run_validate_failure(result) == "Workflow definition is invalid."
