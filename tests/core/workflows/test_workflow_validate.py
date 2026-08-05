"""Tests for the non-raising full workflow definition validation engine."""

from __future__ import annotations

import os
import stat
from importlib import resources
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from getworktree.core.workflows import (
    WORKFLOW_VALIDATOR,
    WorkflowDefinition,
    WorkflowValidationStatus,
    load_workflow_definition,
    validate_workflow_document,
    validate_workflow_result,
)
from getworktree.core.workflows.seeder import (
    WORKFLOW_VALIDATOR as SEEDER_WORKFLOW_VALIDATOR,
)


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
        "version": 1,
        "name": "fix-tests",
        "description": "Iteratively fix failing tests",
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
    return raw


def _dump_yaml(path: Path, payload: object) -> Path:
    if isinstance(payload, str):
        return _write(path, payload)
    text = yaml.safe_dump(payload, sort_keys=False)
    return _write(path, text)


class ValidateWorkflowResultSuccessTests:
    """Success paths for packaged templates and document API."""

    def test_valid_packaged_fix_tests_template(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "fix-tests.yml", _template_text("fix-tests.yml"))
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
        assert result.workflow.version == 1
        assert result.workflow.agent.mode == "fix_failure"
        assert result.workflow.patch.reject_binary_changes is None
        assert path.read_text(encoding="utf-8") == on_disk

    def test_valid_packaged_review_fix_template(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "review-fix.yml", _template_text("review-fix.yml"))

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.name == "review-fix"
        assert result.workflow.agent.mode == "review_remediation"
        assert result.workflow.patch.max_files == 20

    def test_valid_with_optional_reject_binary_changes(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        raw["patch"]["reject_binary_changes"] = True
        path = _dump_yaml(tmp_path / "with-flag.yml", raw)

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.patch.reject_binary_changes is True

    def test_valid_with_cursor_provider(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        raw["agent"]["provider"] = "cursor"
        path = _dump_yaml(tmp_path / "cursor-provider.yml", raw)

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.agent.provider == "cursor"

    def test_valid_with_gemini_provider(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        raw["agent"]["provider"] = "gemini"
        path = _dump_yaml(tmp_path / "gemini-provider.yml", raw)

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.agent.provider == "gemini"

    def test_valid_with_copilot_provider(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        raw["agent"]["provider"] = "copilot"
        path = _dump_yaml(tmp_path / "copilot-provider.yml", raw)

        result = validate_workflow_result(path)

        assert result.ok
        assert result.workflow is not None
        assert result.workflow.agent.provider == "copilot"

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

    def test_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.yml"

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

    def test_not_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "as-dir"
        path.mkdir()

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.NOT_A_FILE
        assert not result.ok
        assert any("WORKFLOW_INVALID_NOT_A_FILE" in e for e in result.errors)
        assert any("Fix:" in e for e in result.errors)

    def test_unreadable(self, tmp_path: Path) -> None:
        path = _dump_yaml(tmp_path / "secret.yml", _valid_raw())
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

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.yml", "version: [\n")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.MALFORMED_YAML
        assert not result.ok
        assert result.raw is None
        assert any("WORKFLOW_INVALID_MALFORMED_YAML" in e for e in result.errors)
        assert any("Fix:" in e for e in result.errors)

    def test_root_not_mapping_list(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "list.yml", "- just\n- a\n- list\n")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.ROOT_NOT_MAPPING
        assert not result.ok
        assert any("WORKFLOW_INVALID_ROOT_NOT_MAPPING" in e for e in result.errors)

    def test_root_not_mapping_null_empty_file(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "empty.yml", "")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.ROOT_NOT_MAPPING
        assert not result.ok
        assert any("WORKFLOW_INVALID_ROOT_NOT_MAPPING" in e for e in result.errors)

    def test_root_not_mapping_scalar(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "scalar.yml", "42\n")

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.ROOT_NOT_MAPPING
        assert not result.ok


class ValidateWorkflowResultSchemaFailureTests:
    """Schema invalid paths and grouped error formatting."""

    def test_unknown_top_level_key(self, tmp_path: Path) -> None:
        raw = _valid_raw(extra_key="nope")
        path = _dump_yaml(tmp_path / "extra.yml", raw)

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.INVALID
        assert not result.ok
        assert result.workflow is None
        assert result.raw == raw
        assert len(result.errors) == 1
        block = result.errors[0]
        assert "WORKFLOW_INVALID_SCHEMA" in block
        assert "Workflow schema validation failed" in block
        assert block.count("WORKFLOW_INVALID_SCHEMA") == 1
        assert "- " in block

    def test_missing_required_section(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        del raw["trigger"]
        path = _dump_yaml(tmp_path / "missing-trigger.yml", raw)

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.INVALID
        assert result.workflow is None
        assert any("WORKFLOW_INVALID_SCHEMA" in e for e in result.errors)
        assert any("trigger" in e for e in result.errors)

    def test_invalid_enum(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        raw["agent"]["provider"] = "openai"
        path = _dump_yaml(tmp_path / "bad-provider.yml", raw)

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.INVALID
        assert result.workflow is None
        block = result.errors[0]
        assert "WORKFLOW_INVALID_SCHEMA" in block
        assert "provider" in block

    def test_schema_failure_skips_semantic(self, tmp_path: Path) -> None:
        raw = _valid_raw()
        del raw["name"]
        path = _dump_yaml(tmp_path / "no-name.yml", raw)

        result = validate_workflow_result(path)

        assert result.status == WorkflowValidationStatus.INVALID
        joined = "\n".join(result.errors)
        assert "WORKFLOW_INVALID_SCHEMA" in joined
        assert "WORKFLOW_SEM_" not in joined


class ValidateWorkflowResultModelAndSemanticTests:
    """Defensive model mapping and semantic rule surface."""

    def test_model_mapping_failure_after_schema(self) -> None:
        raw = _valid_raw()
        with patch.object(
            WorkflowDefinition,
            "model_validate",
            side_effect=ValueError("boom"),
        ):
            result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.status == WorkflowValidationStatus.INVALID
        assert result.workflow is None
        assert result.raw == raw
        assert len(result.errors) == 1
        assert "WORKFLOW_INVALID_MODEL" in result.errors[0]
        assert "boom" in result.errors[0]

    def test_semantic_max_attempts_when_bypassed(self) -> None:
        raw = _valid_raw()
        workflow = WorkflowDefinition.model_validate(raw)
        object.__setattr__(workflow.iteration, "max_attempts", 0)

        with (
            patch.object(
                WORKFLOW_VALIDATOR,
                "validate",
                return_value=type("R", (), {"ok": True, "errors": []})(),
            ),
            patch.object(WorkflowDefinition, "model_validate", return_value=workflow),
        ):
            result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.status == WorkflowValidationStatus.INVALID
        assert result.workflow is None
        assert any("WORKFLOW_SEM_MAX_ATTEMPTS" in e for e in result.errors)

    def test_semantic_timeout_when_bypassed(self) -> None:
        raw = _valid_raw()
        workflow = WorkflowDefinition.model_validate(raw)
        object.__setattr__(workflow.trigger, "timeout_seconds", 0)

        with (
            patch.object(
                WORKFLOW_VALIDATOR,
                "validate",
                return_value=type("R", (), {"ok": True, "errors": []})(),
            ),
            patch.object(WorkflowDefinition, "model_validate", return_value=workflow),
        ):
            result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.status == WorkflowValidationStatus.INVALID
        assert any("WORKFLOW_SEM_TIMEOUT" in e for e in result.errors)

    def test_semantic_patch_limit_when_bypassed(self) -> None:
        raw = _valid_raw()
        workflow = WorkflowDefinition.model_validate(raw)
        object.__setattr__(workflow.patch, "max_files", 0)

        with (
            patch.object(
                WORKFLOW_VALIDATOR,
                "validate",
                return_value=type("R", (), {"ok": True, "errors": []})(),
            ),
            patch.object(WorkflowDefinition, "model_validate", return_value=workflow),
        ):
            result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.status == WorkflowValidationStatus.INVALID
        assert any("WORKFLOW_SEM_PATCH_LIMIT" in e for e in result.errors)

    def test_semantic_stop_when_empty_when_bypassed(self) -> None:
        raw = _valid_raw()
        workflow = WorkflowDefinition.model_validate(raw)
        object.__setattr__(workflow.iteration, "stop_when", [])

        with (
            patch.object(
                WORKFLOW_VALIDATOR,
                "validate",
                return_value=type("R", (), {"ok": True, "errors": []})(),
            ),
            patch.object(WorkflowDefinition, "model_validate", return_value=workflow),
        ):
            result = validate_workflow_document(raw, source_path=Path("in-memory"))

        assert result.status == WorkflowValidationStatus.INVALID
        assert any("WORKFLOW_SEM_STOP_WHEN_EMPTY" in e for e in result.errors)


class LoadWorkflowDefinitionTests:
    """Raising thin wrapper around validate_workflow_result."""

    def test_load_success(self, tmp_path: Path) -> None:
        path = _dump_yaml(tmp_path / "ok.yml", _valid_raw())

        workflow = load_workflow_definition(path)

        assert isinstance(workflow, WorkflowDefinition)
        assert workflow.name == "fix-tests"

    def test_load_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="WORKFLOW_INVALID_NOT_FOUND"):
            load_workflow_definition(tmp_path / "missing.yml")

    def test_load_unreadable_raises(self, tmp_path: Path) -> None:
        path = _dump_yaml(tmp_path / "secret.yml", _valid_raw())
        path.chmod(0)
        try:
            if os.access(path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            with pytest.raises(OSError, match="WORKFLOW_INVALID_UNREADABLE"):
                load_workflow_definition(path)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_load_invalid_raises_value_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.yml", "[]\n")

        with pytest.raises(ValueError, match="WORKFLOW_INVALID_ROOT_NOT_MAPPING"):
            load_workflow_definition(path)


class SharedWorkflowValidatorTests:
    """Shared WORKFLOW_VALIDATOR binding."""

    def test_package_and_seeder_share_same_validator(self) -> None:
        assert WORKFLOW_VALIDATOR is SEEDER_WORKFLOW_VALIDATOR
