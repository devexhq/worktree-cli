"""Tests for Step domain facade."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from worktree.core.step import (
    ExecutionIdentity,
    Step,
    StepAssert,
    StepDefinition,
    StepResult,
    StepType,
)


def test_step_facade_load_and_resolve(tmp_path: Path):
    raw = {
        "id": "echo-test",
        "name": "Echo Test",
        "run": "echo hello",
    }
    step_def = Step.load(raw)
    assert isinstance(step_def, StepDefinition)
    assert step_def.id == "echo-test"

    # load from Path
    step_file = tmp_path / "step.yaml"
    step_file.write_text(yaml.safe_dump(raw), encoding="utf-8")
    loaded_from_path = Step.load(step_file)
    assert loaded_from_path.id == "echo-test"

    # load from str path
    loaded_from_str = Step.load(str(step_file))
    assert loaded_from_str.id == "echo-test"

    # load by id from catalog directory
    catalog_step_dir = tmp_path / ".worktree" / "catalog" / "steps"
    catalog_step_dir.mkdir(parents=True, exist_ok=True)
    (catalog_step_dir / "catalog-step.yaml").write_text(
        yaml.safe_dump({"id": "catalog-step", "run": "echo cat"}),
        encoding="utf-8",
    )
    loaded_by_id = Step.load_by_id("catalog-step", path=tmp_path)
    assert loaded_by_id.id == "catalog-step"
    loaded_via_load_str = Step.load("catalog-step", path=tmp_path)
    assert loaded_via_load_str.id == "catalog-step"

    with pytest.raises(TypeError):
        Step.load(123)  # pyright: ignore[reportArgumentType]

    resolved = Step.resolve(step_def)
    assert resolved.type == StepType.COMMAND
    assert resolved.command == "echo hello"


def test_step_facade_condition_evaluation():
    errors = Step.validate_condition("iteration == 1")
    assert errors == []
    parsed = Step.parse_condition("iteration == 1")
    assert parsed is not None
    assert parsed.left == "iteration"

    res = Step.evaluate_condition("iteration == 1", iteration_index=1)
    assert res.passed is True


def test_step_facade_assertion_evaluation(tmp_path: Path):
    assertion = StepAssert(exit_code=0, output_contains="success")
    result = Step.evaluate_assertions(
        assertion,
        stdout="all success here",
        exit_code=0,
        sandbox_path=tmp_path,
    )
    assert result.passed is True


def test_step_facade_metadata_and_env():
    step_def = StepDefinition(id="test-meta", name="Test Meta", run="echo 1")
    identity = ExecutionIdentity(workflow_name="my-workflow")
    meta = Step.build_metadata(step_def, step_index=2, attempt=1, identity=identity)
    assert meta.step.id == "test-meta"
    assert meta.workflow.name == "my-workflow"

    env = Step.metadata_to_env(meta)
    assert env["WT_STEP_ID"] == "test-meta"
    assert env["WT_WORKFLOW_NAME"] == "my-workflow"


def test_step_facade_run(tmp_path: Path):
    step_def = StepDefinition(id="run-echo", run="echo 'facade test'")
    result = Step.run(step_def, sandbox_path=tmp_path)
    assert isinstance(result, StepResult)
    assert result.status == "completed"
    assert result.exit_code == 0
    assert "facade test" in result.stdout

    prev = Step.previous_step_metadata(result, step_index=1)
    assert prev.id == "run-echo"
    assert prev.exit_code == "0"
