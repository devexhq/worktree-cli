"""Unit tests for step definition schema, models, loader, and resolver."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from getworktree.core.step import (
    FailureAction,
    StepDefinition,
    StepNotFoundError,
    StepType,
    StepValidationError,
    load_step_by_id,
    load_step_definition,
)


def test_step_definition_command_valid():
    step = StepDefinition(
        id="step_pytest",
        name="run-pytest",
        type=StepType.COMMAND,
        description="Run pytest suite",
        command="pytest tests/",
        timeout_seconds=60,
        failure_action=FailureAction.ABORT,
    )
    assert step.id == "step_pytest"
    assert step.type == StepType.COMMAND
    assert step.command == "pytest tests/"
    assert step.timeout_seconds == 60
    assert step.failure_action == FailureAction.ABORT


def test_step_definition_agent_valid():
    step = StepDefinition(
        id="step_refactor",
        name="refactor-code",
        type=StepType.AGENT,
        description="Refactor code for performance",
        prompt="Refactor loop logic",
        agent="claude-3-5-sonnet",
        tools=["edit_file", "run_linter"],
    )
    assert step.type == StepType.AGENT
    assert step.prompt == "Refactor loop logic"
    assert step.agent == "claude-3-5-sonnet"
    assert step.tools == ["edit_file", "run_linter"]


def test_step_definition_script_valid():
    step = StepDefinition(
        id="step_script",
        name="run-script",
        type=StepType.SCRIPT,
        description="Run custom script",
        script_path="scripts/build.sh",
    )
    assert step.type == StepType.SCRIPT
    assert step.script_path == "scripts/build.sh"


def test_step_definition_missing_required_type_fields():
    with pytest.raises(ValidationError, match="Command steps must specify"):
        StepDefinition(
            id="s1",
            name="n1",
            type=StepType.COMMAND,
            description="desc",
        )

    with pytest.raises(ValidationError, match="Agent steps must specify"):
        StepDefinition(
            id="s2",
            name="n2",
            type=StepType.AGENT,
            description="desc",
        )

    with pytest.raises(ValidationError, match="Script steps must specify"):
        StepDefinition(
            id="s3",
            name="n3",
            type=StepType.SCRIPT,
            description="desc",
        )


def test_step_definition_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        StepDefinition(
            id="s1",
            name="n1",
            type=StepType.COMMAND,
            description="desc",
            command="echo 1",
            unknown_key="invalid",
        )


def test_load_step_definition_valid(tmp_path: Path):
    step_file = tmp_path / "step_verify.yaml"
    step_file.write_text(
        """
id: step_verify
name: verify-build
type: command
description: Run build verification
command: inv test
timeout_seconds: 300
failure_action: retry
""",
        encoding="utf-8",
    )

    step = load_step_definition(step_file)
    assert step.id == "step_verify"
    assert step.name == "verify-build"
    assert step.type == StepType.COMMAND
    assert step.command == "inv test"
    assert step.timeout_seconds == 300
    assert step.failure_action == FailureAction.RETRY


def test_load_step_definition_not_found(tmp_path: Path):
    missing_path = tmp_path / "nonexistent.yaml"
    with pytest.raises(StepNotFoundError, match="not found"):
        load_step_definition(missing_path)


def test_load_step_definition_malformed_yaml(tmp_path: Path):
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("id: [unclosed list", encoding="utf-8")
    with pytest.raises(StepValidationError, match="Failed to read or parse YAML"):
        load_step_definition(invalid_yaml)


def test_load_step_definition_root_not_mapping(tmp_path: Path):
    scalar_yaml = tmp_path / "scalar.yaml"
    scalar_yaml.write_text("just a string", encoding="utf-8")
    with pytest.raises(StepValidationError, match="must be a mapping object"):
        load_step_definition(scalar_yaml)


def test_load_step_definition_schema_validation_failure(tmp_path: Path):
    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text(
        """
id: bad_step
name: bad
type: command
description: Missing command field
""",
        encoding="utf-8",
    )
    with pytest.raises(StepValidationError, match="validation failed"):
        load_step_definition(bad_schema)


def test_load_step_by_id_success(tmp_path: Path):
    steps_dir = tmp_path / ".worktree" / "templates" / "steps"
    steps_dir.mkdir(parents=True)

    step_file = steps_dir / "step_lint.yaml"
    step_file.write_text(
        """
id: step_lint_id
name: run-lint
type: command
description: Run linter
command: ruff check .
""",
        encoding="utf-8",
    )

    # Resolve by direct filename
    step1 = load_step_by_id("step_lint", cwd=tmp_path)
    assert step1.id == "step_lint_id"

    # Resolve by id field
    step2 = load_step_by_id("step_lint_id", cwd=tmp_path)
    assert step2.name == "run-lint"

    # Resolve by name slug
    step3 = load_step_by_id("run-lint", cwd=tmp_path)
    assert step3.id == "step_lint_id"


def test_load_step_by_id_missing_directory(tmp_path: Path):
    with pytest.raises(StepNotFoundError, match=r"Directory .* does not exist"):
        load_step_by_id("step_test", cwd=tmp_path)


def test_load_step_by_id_not_found(tmp_path: Path):
    steps_dir = tmp_path / ".worktree" / "templates" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "other.yaml").write_text(
        """
id: other_id
name: other-name
type: command
description: Other
command: echo other
""",
        encoding="utf-8",
    )

    with pytest.raises(StepNotFoundError, match="not found in"):
        load_step_by_id("nonexistent_step", cwd=tmp_path)
