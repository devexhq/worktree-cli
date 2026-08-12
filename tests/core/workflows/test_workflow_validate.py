"""Tests for the non-raising full workflow definition validation engine V1."""

from __future__ import annotations

import os
import stat
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from getworktree.core.step import StepAssert, StepDefinition
from getworktree.core.workflows import (
    WORKFLOW_VALIDATOR,
    WorkflowDefinition,
    WorkflowLoadError,
    WorkflowValidationError,
    WorkflowValidationStatus,
    load_workflow_definition,
    validate_workflow_document,
    validate_workflow_inputs,
    validate_workflow_result,
)
from getworktree.core.workflows.seeder import (
    WORKFLOW_VALIDATOR as SEEDER_WORKFLOW_VALIDATOR,
)
from tests.helpers import FileSystem


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.workflows")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


def _valid_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "version": "1.0",
        "name": "Feature Dev with Review Loop",
        "id": "feature-dev-v1",
        "description": "Iterative AI feature development workflow with test and review gates",
        "timeout_seconds": 3600,
        "env": {
            "PYTHONPATH": ".",
        },
        "inputs": {
            "prompt": {
                "description": "The feature or fix prompt",
                "required": True,
            }
        },
        "steps": [
            {
                "id": "prepare-sandbox",
                "uses": "wt/git-sync-base",
                "on_failure": "abort",
            },
            {
                "id": "dev-cycle",
                "type": "loop",
                "max_iterations": 5,
                "until": [
                    "steps.run-tests.exit_code == 0",
                ],
                "on_max_iterations": "prompt_user",
                "do": [
                    {
                        "id": "run-tests",
                        "run": "pytest tests/ -q",
                        "on_failure": "continue",
                    }
                ],
            },
            {
                "id": "lint-formatting",
                "run": "ruff check . && ruff format --check .",
                "on_failure": "prompt_user",
            },
        ],
    }
    raw.update(overrides)
    return raw


def _dump_yaml(path: Path, payload: object) -> Path:
    if isinstance(payload, str):
        return _write(path, payload)
    text = yaml.safe_dump(payload, sort_keys=False)
    return _write(path, text)


class ValidateWorkflowResultSuccessTests:
    """Success paths for packaged templates and document API."""

    def test_valid_packaged_fix_tests_template(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "fix-tests.yml", _template_text("fix-tests.yml"))
        on_disk = path.read_text(encoding="utf-8")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.VALID
        assert result.ok
        assert result.errors == []
        assert result.warnings == []
        assert result.source_path == path.resolve()
        assert result.raw is not None
        assert result.workflow is not None
        assert result.workflow.name == "fix-tests"
        assert result.workflow.id == "fix-tests"
        assert result.workflow.version == "1.0"
        assert len(result.workflow.steps) == 1
        assert path.read_text(encoding="utf-8") == on_disk

    def test_valid_packaged_review_fix_template(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "review-fix.yml", _template_text("review-fix.yml"))

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.name == "review-fix"
        assert result.workflow.id == "review-fix"

    def test_validate_workflow_document_memory_source_path(self) -> None:
        raw = _valid_raw()
        source = Path("in-memory")

        result = validate_workflow_document(raw, source_path=source)

        assert result.ok
        assert result.source_path == source
        assert result.workflow is not None
        assert result.raw == raw


class ValidateWorkflowResultIoFailureTests:
    """IO and parse failure classification."""

    def test_not_found(self, fs: FileSystem) -> None:
        path = fs.base_path / "missing.yml"

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.NOT_FOUND
        assert not result.ok
        assert result.workflow is None
        assert result.raw is None
        assert result.warnings == []
        assert len(result.errors) == 1
        msg = result.errors[0]
        assert "WORKFLOW_INVALID_NOT_FOUND" in msg
        assert str(path.resolve()) in msg
        assert "wt workflow list" in msg
        assert "Fix:" in msg

    def test_not_a_file(self, fs: FileSystem) -> None:
        path = fs.base_path / "as-dir"
        path.mkdir()

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.NOT_A_FILE
        assert not result.ok
        assert any("WORKFLOW_INVALID_NOT_A_FILE" in e for e in result.errors)
        assert any("Fix:" in e for e in result.errors)

    def test_unreadable(self, fs: FileSystem) -> None:
        path = _dump_yaml(fs.base_path / "secret.yml", _valid_raw())
        path.chmod(0)
        try:
            result = validate_workflow_result(path)
            if os.access(path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            assert result.status == WorkflowValidationStatus.UNREADABLE
            assert not result.ok
            assert result.warnings == []
            assert any("WORKFLOW_INVALID_UNREADABLE" in e for e in result.errors)
            assert any("Fix:" in e for e in result.errors)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_malformed_yaml(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "bad.yml", "version: [\n")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.MALFORMED_YAML
        assert not result.ok
        assert result.raw is None
        assert any("WORKFLOW_INVALID_MALFORMED_YAML" in e for e in result.errors)
        assert any("Fix:" in e for e in result.errors)

    def test_root_not_mapping_list(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "list.yml", "- just\n- a\n- list\n")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.ROOT_NOT_MAPPING
        assert not result.ok
        assert any("WORKFLOW_INVALID_ROOT_NOT_MAPPING" in e for e in result.errors)

    def test_root_not_mapping_null_empty_file(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "empty.yml", "")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.ROOT_NOT_MAPPING
        assert not result.ok
        assert any("WORKFLOW_INVALID_ROOT_NOT_MAPPING" in e for e in result.errors)


class ValidateWorkflowResultMutualExclusivityTests:
    """Mutual exclusivity tests between uses and run."""

    def test_step_with_both_uses_and_run_fails(self, fs: FileSystem) -> None:
        raw = _valid_raw()
        raw["steps"].append(
            {
                "id": "run-tests",
                "uses": "wt/run-tests",
                "run": "pytest",
            }
        )
        path = _dump_yaml(fs.base_path / "both.yml", raw)

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.INVALID
        assert not result.ok
        assert len(result.errors) == 1
        assert "WORKFLOW_INVALID_SCHEMA" in result.errors[0]

    def test_model_validates_uses_and_run_mutual_exclusivity(self) -> None:
        with pytest.raises(ValueError, match="cannot be combined with"):
            StepDefinition(
                id="run-tests",
                uses="wt/run-tests",
                run="pytest",
            )

    def test_model_validates_neither_uses_nor_run(self) -> None:
        with pytest.raises(ValueError, match="must specify one of 'run', 'uses', or 'type'"):
            StepDefinition(id="run-tests")


class ValidateWorkflowInputsTests:
    """Workflow input validation and default resolution tests."""

    def test_input_resolution_success_with_defaults(self) -> None:
        raw = _valid_raw()
        raw["inputs"]["optional_flag"] = {
            "description": "Optional flag",
            "required": False,
            "default": "verbose",
        }
        workflow = WorkflowDefinition.model_validate(raw)

        resolved = validate_workflow_inputs(workflow, {"prompt": "Fix bug"})

        assert resolved["prompt"] == "Fix bug"
        assert resolved["optional_flag"] == "verbose"

    def test_missing_required_input_raises_validation_error(self) -> None:
        raw = _valid_raw()
        workflow = WorkflowDefinition.model_validate(raw)

        with pytest.raises(WorkflowValidationError, match="Missing required input"):
            validate_workflow_inputs(workflow, {})


class LoadWorkflowDefinitionTests:
    """Raising thin wrapper around validate_workflow_result."""

    def test_load_success(self, fs: FileSystem) -> None:
        path = _dump_yaml(fs.base_path / "ok.yml", _valid_raw())

        workflow = load_workflow_definition(path)

        assert isinstance(workflow, WorkflowDefinition)
        assert workflow.name == "Feature Dev with Review Loop"
        assert workflow.id == "feature-dev-v1"

    def test_load_not_found_raises(self, fs: FileSystem) -> None:
        with pytest.raises(FileNotFoundError, match="WORKFLOW_INVALID_NOT_FOUND"):
            load_workflow_definition(fs.base_path / "missing.yml")

    def test_load_malformed_yaml_raises_load_error(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "bad.yml", "version: [\n")

        with pytest.raises(WorkflowLoadError, match="WORKFLOW_INVALID_MALFORMED_YAML"):
            load_workflow_definition(path)

    def test_load_invalid_raises_validation_error(self, fs: FileSystem) -> None:
        path = _write(fs.base_path / "bad.yml", "[]\n")

        with pytest.raises(WorkflowValidationError, match="WORKFLOW_INVALID_ROOT_NOT_MAPPING"):
            load_workflow_definition(path)


class SharedWorkflowValidatorTests:
    """Shared WORKFLOW_VALIDATOR binding."""

    def test_package_and_seeder_share_same_validator(self) -> None:
        assert WORKFLOW_VALIDATOR is SEEDER_WORKFLOW_VALIDATOR


class StepAssertSchemaAndModelTests:
    """Schema/model coverage for extended step assert fields."""

    def test_standard_step_assert_alias_round_trip(self) -> None:
        """``assert`` key maps onto ``assert_`` and dumps back under the alias."""
        step = StepDefinition.model_validate(
            {
                "id": "run-tests",
                "run": "pytest",
                "assert": {
                    "exit_code": [0, 2],
                    "file_exists": "dist/app.bin",
                    "file_not_exists": ["tmp/lock"],
                    "file_not_empty": ["dist/app.bin", "dist/manifest.json"],
                },
            }
        )

        dumped = step.model_dump(by_alias=True)
        assert "assert_" not in dumped
        assert dumped["assert"]["exit_code"] == [0, 2]
        assert dumped["assert"]["file_exists"] == "dist/app.bin"
        assert dumped["assert"]["file_not_exists"] == ["tmp/lock"]
        assert dumped["assert"]["file_not_empty"] == ["dist/app.bin", "dist/manifest.json"]

        reloaded = StepDefinition.model_validate(dumped)
        assert reloaded.assert_ is not None
        assert reloaded.assert_.exit_code == [0, 2]

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("file_exists", "/etc/passwd"),
            ("file_exists", "../secrets.txt"),
            ("file_exists", ""),
            ("file_not_exists", "C:/Windows/system32"),
            ("file_not_empty", ["ok.txt", "a/../../x"]),
            ("file_not_empty", "\\..\\escape.txt"),
        ],
    )
    def test_step_assert_path_safety_rejects_unsafe_paths(self, field_name: str, value: str | list[str]) -> None:
        with pytest.raises(ValidationError, match=field_name):
            StepAssert(**{field_name: value})

        with pytest.raises(ValidationError, match=field_name):
            StepDefinition(
                id="run-tests",
                run="pytest",
                assert_=StepAssert(**{field_name: value}),
            )

    def test_workflow_schema_accepts_extended_assert_block(self) -> None:
        raw = _valid_raw()
        raw["steps"][0]["assert"] = {
            "exit_code": [0, 1],
            "file_exists": "dist/app.bin",
            "file_not_exists": ["tmp/lock"],
            "file_not_empty": ["dist/app.bin", "dist/manifest.json"],
            "output_contains": "ok",
        }

        result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.ok
        assert result.workflow is not None
        step = result.workflow.steps[0]
        assert isinstance(step, StepDefinition)
        assert step.assert_ is not None
        assert step.assert_.exit_code == [0, 1]
        assert step.assert_.file_exists == "dist/app.bin"
        assert step.assert_.file_not_exists == ["tmp/lock"]
        assert step.assert_.file_not_empty == ["dist/app.bin", "dist/manifest.json"]

    def test_workflow_schema_rejects_empty_exit_code_list(self) -> None:
        raw = _valid_raw()
        raw["steps"][0]["assert"] = {"exit_code": []}

        result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert not result.ok
        assert result.status == WorkflowValidationStatus.INVALID
        joined = "\n".join(result.errors)
        assert "WORKFLOW_INVALID_SCHEMA" in joined
        assert "exit_code" in joined
