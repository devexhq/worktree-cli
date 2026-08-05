"""Tests for `getworktree.common.schema_validation`."""

from __future__ import annotations

from importlib import resources

from getworktree.common.schema_validation import SchemaValidator

WORKFLOW_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas") / "workflow_v1.json"
)


class ValidateWorkflowV1Tests:
    """Tests for validating workflow payloads against the v1 workflow schema."""

    def test_validate_workflow_v1_accepts_starter_template(self) -> None:
        workflow_obj = {
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

        result = WORKFLOW_VALIDATOR.validate(workflow_obj)

        assert result.ok
        assert result.errors == []

    def test_validate_workflow_v1_reports_readable_errors(self) -> None:
        invalid_workflow = {
            "version": 1,
            "description": "missing name",
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
                "stop_when": ["trigger_passes"],
            },
            "sandbox": {
                "auto_clean": True,
                "keep_on_failure": True,
            },
            "approval": {
                "require_before_apply": True,
            },
            "context": {
                "include": ["trigger_output"],
            },
            "patch": {
                "strategy": "unified_diff",
                "max_files": 30,
                "max_patch_kb": 1024,
            },
        }

        result = WORKFLOW_VALIDATOR.validate(invalid_workflow)

        assert not result.ok
        assert any("name" in error for error in result.errors)
