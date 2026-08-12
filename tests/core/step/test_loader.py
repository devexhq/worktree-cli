"""Unit tests for step definition YAML loading helpers."""

import pytest

from getworktree.core.step import (
    StepDefinition,
    StepNotFoundError,
    StepType,
    StepValidationError,
    load_step_by_id,
    load_step_definition,
)
from tests.helpers import FileSystem


def test_load_step_definition_valid(fs: FileSystem):
    step_file = fs.write_file(
        "step_verify.yaml",
        """
id: step_verify
name: verify-build
type: command
description: Run build verification
command: inv test
timeout_seconds: 300
on_failure: retry
""",
    )

    step = load_step_definition(step_file)
    assert step.id == "step_verify"
    assert step.name == "verify-build"
    assert step.type == StepType.COMMAND
    assert step.command == "inv test"
    assert step.timeout_seconds == 300
    assert step.on_failure.action.value == "retry"


def test_load_step_definition_not_found(fs: FileSystem):
    missing_path = fs.base_path / "nonexistent.yaml"
    with pytest.raises(StepNotFoundError, match="not found"):
        load_step_definition(missing_path)


def test_load_step_definition_malformed_yaml(fs: FileSystem):
    invalid_yaml = fs.write_file("invalid.yaml", "id: [unclosed list")
    with pytest.raises(StepValidationError, match="Failed to read or parse YAML"):
        load_step_definition(invalid_yaml)


def test_load_step_definition_root_not_mapping(fs: FileSystem):
    scalar_yaml = fs.write_file("scalar.yaml", "just a string")
    with pytest.raises(StepValidationError, match="must be a mapping object"):
        load_step_definition(scalar_yaml)


def test_load_step_definition_schema_validation_failure(fs: FileSystem):
    bad_schema = fs.write_file(
        "bad_schema.yaml",
        """
id: bad_step
type: command
description: Missing command field
""",
    )
    with pytest.raises(StepValidationError, match="validation failed"):
        load_step_definition(bad_schema)


def test_load_step_by_id_success(fs: FileSystem):
    fs.write_file(
        ".worktree/catalog/steps/step_lint.yaml",
        """
id: step_lint_id
name: run-lint
type: command
description: Run linter
command: ruff check .
""",
    )

    # Resolve by direct filename
    step1 = load_step_by_id("step_lint", cwd=fs.base_path)
    assert step1.id == "step_lint_id"

    # Resolve by id field
    step2 = load_step_by_id("step_lint_id", cwd=fs.base_path)
    assert step2.name == "run-lint"

    # Resolve by name slug
    step3 = load_step_by_id("run-lint", cwd=fs.base_path)
    assert step3.id == "step_lint_id"


def test_load_step_by_id_missing_directory(fs: FileSystem):
    with pytest.raises(StepNotFoundError, match=r"Directory .* does not exist"):
        load_step_by_id("step_test", cwd=fs.base_path)


def test_load_step_by_id_not_found(fs: FileSystem):
    fs.write_file(
        ".worktree/catalog/steps/other.yaml",
        """
id: other_id
name: other-name
type: command
description: Other
command: echo other
""",
    )

    with pytest.raises(StepNotFoundError, match="not found in"):
        load_step_by_id("nonexistent_step", cwd=fs.base_path)


def test_load_step_definition_returns_step_definition_instance(fs: FileSystem):
    step_file = fs.write_file("step.yaml", "id: s1\nrun: echo 1\n")
    step = load_step_definition(step_file)
    assert isinstance(step, StepDefinition)
