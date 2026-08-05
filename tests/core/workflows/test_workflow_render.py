"""Tests for pure workflow show text formatters."""

from __future__ import annotations

from pathlib import Path

from getworktree.core.workflows.models import WorkflowDefinition
from getworktree.core.workflows.render import (
    format_workflow_show_resolve_failure,
    format_workflow_show_success,
    format_workflow_show_validate_failure,
)
from getworktree.core.workflows.resolve import (
    WorkflowResolveResult,
    WorkflowResolveStatus,
)
from getworktree.core.workflows.validate import (
    WorkflowValidationResult,
    WorkflowValidationStatus,
)


def _sample_workflow(**overrides: object) -> WorkflowDefinition:
    raw: dict = {
        "version": 1,
        "name": "fix-tests",
        "description": "Iteratively fix failing tests until they pass or attempts are exhausted",
        "trigger": {
            "command": "pytest",
            "args": [],
            "timeout_seconds": 600,
        },
        "agent": {
            "provider": "local",
            "mode": "fix_failure",
            "timeout_seconds": 120,
        },
        "iteration": {
            "max_attempts": 5,
            "stop_when": ["trigger_passes", "unfixable", "user_abort"],
        },
        "sandbox": {
            "auto_clean": True,
            "keep_on_failure": True,
        },
        "approval": {
            "require_before_apply": True,
        },
        "context": {
            "include": ["trigger_output", "changed_files", "relevant_source"],
        },
        "patch": {
            "strategy": "unified_diff",
            "max_files": 30,
            "max_patch_kb": 1024,
        },
    }
    raw.update(overrides)
    return WorkflowDefinition.model_validate(raw)


class FormatWorkflowShowSuccessTests:
    """Normative success layout for format_workflow_show_success."""

    def test_full_layout_matches_template_shape(self, tmp_path: Path) -> None:
        source = (tmp_path / "fix-tests.yml").resolve()
        text = format_workflow_show_success(_sample_workflow(), source_path=source)

        assert text.endswith("\n")
        expected = (
            f"Workflow: fix-tests\n"
            f"Source: {source.as_posix()}\n"
            f"Status: valid\n"
            f"\n"
            f"Description:\n"
            f"  Iteratively fix failing tests until they pass or attempts are exhausted\n"
            f"\n"
            f"Trigger:\n"
            f"  command: pytest\n"
            f"  args: []\n"
            f"  timeout_seconds: 600\n"
            f"\n"
            f"Agent:\n"
            f"  provider: local\n"
            f"  mode: fix_failure\n"
            f"  timeout_seconds: 120\n"
            f"\n"
            f"Iteration:\n"
            f"  max_attempts: 5\n"
            f'  stop_when: ["trigger_passes", "unfixable", "user_abort"]\n'
            f"\n"
            f"Sandbox:\n"
            f"  auto_clean: true\n"
            f"  keep_on_failure: true\n"
            f"\n"
            f"Approval:\n"
            f"  require_before_apply: true\n"
            f"\n"
            f"Context:\n"
            f'  include: ["trigger_output", "changed_files", "relevant_source"]\n'
            f"\n"
            f"Patch:\n"
            f"  strategy: unified_diff\n"
            f"  max_files: 30\n"
            f"  max_patch_kb: 1024\n"
            f"  reject_binary_changes: null\n"
        )
        assert text == expected

    def test_args_and_lists_and_bool_null(self, tmp_path: Path) -> None:
        workflow = _sample_workflow()
        data = workflow.model_dump()
        data["trigger"]["args"] = ["-q", "tests"]
        data["patch"]["reject_binary_changes"] = False
        data["description"] = "line one\nline two"
        workflow = WorkflowDefinition.model_validate(data)
        source = (tmp_path / "x.yml").resolve()

        text = format_workflow_show_success(workflow, source_path=source)

        assert '  args: ["-q", "tests"]\n' in text
        assert "  reject_binary_changes: false\n" in text
        assert "Description:\n  line one\n  line two\n" in text

    def test_warnings_section_and_status_token(self, tmp_path: Path) -> None:
        source = (tmp_path / "fix-tests.yml").resolve()
        text = format_workflow_show_success(
            _sample_workflow(),
            source_path=source,
            warnings=[
                "Duplicate workflow name 'fix-tests' (WORKFLOW_RESOLVE_DUPLICATE_NAME).",
                "second\ncontinued",
            ],
        )

        lines = text.splitlines()
        assert lines[2] == "Status: valid with warnings"
        assert lines[3] == ""
        assert lines[4] == "Warnings:"
        assert lines[5].startswith("- Duplicate workflow name")
        assert lines[6] == "- second"
        assert lines[7] == "  continued"
        assert lines[8] == ""
        assert lines[9] == "Description:"


class FormatWorkflowShowFailureTests:
    """Failure body formatters."""

    def test_resolve_failure_joins_errors(self, tmp_path: Path) -> None:
        result = WorkflowResolveResult(
            status=WorkflowResolveStatus.NOT_FOUND,
            name="missing",
            workflows_dir=tmp_path,
            errors=["err-a", "err-b"],
        )
        assert format_workflow_show_resolve_failure(result) == "err-a\n\nerr-b"

    def test_resolve_failure_fallback(self, tmp_path: Path) -> None:
        result = WorkflowResolveResult(
            status=WorkflowResolveStatus.NOT_FOUND,
            name="missing",
            workflows_dir=tmp_path,
            errors=[],
        )
        assert (
            format_workflow_show_resolve_failure(result)
            == "Failed to resolve workflow."
        )

    def test_validate_failure_joins_errors(self, tmp_path: Path) -> None:
        result = WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=tmp_path / "x.yml",
            errors=["schema bad", "more"],
        )
        assert format_workflow_show_validate_failure(result) == "schema bad\n\nmore"

    def test_validate_failure_fallback(self, tmp_path: Path) -> None:
        result = WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=tmp_path / "x.yml",
            errors=[],
        )
        assert (
            format_workflow_show_validate_failure(result)
            == "Workflow definition is invalid."
        )
