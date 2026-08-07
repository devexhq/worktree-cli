"""Tests for `getworktree.common.schema_validation`."""

from __future__ import annotations

from importlib import resources

from getworktree.common.schema_validation import SchemaValidator

WORKFLOW_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas.v1") / "workflow.json"
)


class ValidateWorkflowV1Tests:
    """Tests for validating workflow payloads against the v1 workflow schema."""

    def test_validate_workflow_v1_accepts_starter_template(self) -> None:
        workflow_obj = {
            "version": "1.0",
            "name": "Feature Dev",
            "id": "feature-dev",
            "description": "Iteratively fix failing tests",
            "steps": [
                {
                    "id": "run-tests",
                    "run": "pytest tests/ -q",
                    "on_failure": "continue",
                }
            ],
        }

        result = WORKFLOW_VALIDATOR.validate(workflow_obj)

        assert result.ok
        assert result.errors == []

    def test_validate_workflow_v1_reports_readable_errors(self) -> None:
        invalid_workflow = {
            "version": 1,
            "id": "test-id",
            "description": "missing name",
            "steps": [
                {
                    "id": "run-tests",
                    "run": "pytest",
                }
            ],
        }

        result = WORKFLOW_VALIDATOR.validate(invalid_workflow)

        assert not result.ok
        assert any("name" in error for error in result.errors)
