"""Tests for Step domain handle and resolver."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.helpers import FileSystem
from worktree.common.models import FailurePolicy, OnFailureSpec
from worktree.core.step import (
    ExecutionIdentity,
    Step,
    StepAssert,
    StepDefinition,
    StepType,
)


class StepHandleTests:
    """Unit tests for the Step domain handle class."""

    def test_step_load_and_resolve(self, tmp_path: Path) -> None:
        raw = {
            "id": "echo-test",
            "name": "Echo Test",
            "run": "echo hello",
        }
        step = Step(definition=raw)
        assert isinstance(step.instance, StepDefinition)
        assert step.instance.id == "echo-test"

        # load from Path
        step_file = tmp_path / "step.yaml"
        step_file.write_text(yaml.safe_dump(raw), encoding="utf-8")
        loaded_from_path = Step.load_by_path(step_file)
        assert loaded_from_path is not None
        assert loaded_from_path.instance.id == "echo-test"

        # load from str path
        loaded_from_str = Step.load_by_path(str(step_file))
        assert loaded_from_str is not None
        assert loaded_from_str.instance.id == "echo-test"

        # load by id from catalog directory
        catalog_step_dir = tmp_path / ".worktree" / "catalog" / "steps"
        catalog_step_dir.mkdir(parents=True, exist_ok=True)
        (catalog_step_dir / "catalog-step.yaml").write_text(
            yaml.safe_dump({"id": "catalog-step", "run": "echo cat"}),
            encoding="utf-8",
        )
        loaded_by_id = Step.load_by_name("catalog-step", path=tmp_path)
        assert loaded_by_id is not None
        assert loaded_by_id.instance.id == "catalog-step"
        loaded_via_load_str = Step.load("catalog-step", path=tmp_path)
        assert loaded_via_load_str is not None
        assert loaded_via_load_str.instance.id == "catalog-step"

        with pytest.raises(TypeError):
            Step.load(123)  # pyright: ignore[reportArgumentType]

        resolved = step.resolve()
        assert resolved is not None
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "echo hello"

    def test_step_condition_evaluation(self) -> None:
        errors = Step.validate_condition("iteration == 1")
        assert errors == []
        parsed = Step.parse_condition("iteration == 1")
        assert parsed is not None
        assert parsed.left == "iteration"

        res = Step.evaluate_condition("iteration == 1", iteration_index=1)
        assert res.passed is True

    def test_step_assertion_evaluation(self, tmp_path: Path) -> None:
        assertion = StepAssert(exit_code=0, output_contains="success")
        result = Step.evaluate_assertions(
            assertion,
            stdout="all success here",
            exit_code=0,
            sandbox_path=tmp_path,
        )
        assert result.passed is True

    def test_step_metadata_and_env(self) -> None:
        step_def = StepDefinition(id="test-meta", name="Test Meta", run="echo 1")
        identity = ExecutionIdentity(blueprint_name="my-blueprint", blueprint_key="wt/my-blueprint")
        meta = Step.build_metadata(step_def, step_index=2, attempt=1, identity=identity)
        assert meta.step.id == "test-meta"
        assert meta.blueprint.name == "my-blueprint"
        assert meta.blueprint.key == "wt/my-blueprint"

        env = Step.metadata_to_env(meta)
        assert env["WT_STEP_ID"] == "test-meta"
        assert env["WT_BLUEPRINT_NAME"] == "my-blueprint"
        assert env["WT_BLUEPRINT_SHA"] == "wt/my-blueprint"


class StepResolverTests:
    """Unit tests for resolving run shorthands, inline step types, and catalog uses references."""

    def test_resolve_run_step_synthesizes_command_step(self) -> None:
        step = Step(instance=StepDefinition(id="run-tests", run="pytest tests/ -q"))

        resolved = step.resolve()

        assert resolved is not None
        assert resolved.id == "run-tests"
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "pytest tests/ -q"
        assert resolved.uses is None
        assert resolved.run is None

    def test_resolve_inline_type_step_passes_through_unchanged(self) -> None:
        step = Step(instance=StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi"))

        resolved = step.resolve()

        assert resolved == StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")

    def test_resolve_uses_step_loads_referenced_definition(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="lint", command="ruff check .")

        step = Step(instance=StepDefinition(id="lint-step", uses="lint"))

        resolved = step.resolve(path=fs.base_path)

        assert resolved is not None
        assert resolved.id == "lint-step"
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "ruff check ."
        assert resolved.name == "run-lint"

    def test_resolve_uses_step_overrides_use_referencing_step_fields(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="base", name="base-name", command="echo base", timeout_seconds=30)

        step = Step(instance=StepDefinition(id="derived", uses="base", name="derived-name", timeout_seconds=90))

        resolved = step.resolve(path=fs.base_path)

        assert resolved is not None
        assert resolved.name == "derived-name"
        assert resolved.timeout_seconds == 90
        assert resolved.command == "echo base"

    def test_resolve_uses_step_merges_on_failure_when_referencing_step_overrides(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="base", command="echo base", on_failure="continue")

        step = Step(
            instance=StepDefinition(id="derived", uses="base", on_failure=OnFailureSpec(action=FailurePolicy.ABORT))
        )

        resolved = step.resolve(path=fs.base_path)
        assert resolved is not None
        assert resolved.on_failure == OnFailureSpec(action=FailurePolicy.ABORT)

    def test_resolve_step_without_run_uses_or_type_returns_none(self) -> None:
        step = Step(instance=StepDefinition.model_construct(id="broken", uses=None, run=None, type=None))

        assert step.resolve() is None
