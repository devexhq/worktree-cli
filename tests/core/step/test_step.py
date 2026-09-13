from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.common.models import FailurePolicy, OnFailureSpec
from worktree.core.step import Step, StepDefinition, StepType, StepValidationError, resolve_step_definition

pytestmark = pytest.mark.unit


class StepShorthandExpansionTests:
    """Unit tests verifying shorthand step expansion contracts."""

    def test_step_loader_expands_run_shorthand_preserving_environment(self) -> None:
        """Shorthand 'run' step expands to command type preserving explicit environment variables."""
        raw = {"id": "test", "run": "npm test", "env": {"CI": "1"}}
        step = resolve_step_definition(raw)
        assert_model_equal(
            step,
            StepDefinition(
                id="test",
                type=StepType.COMMAND,
                command="npm test",
                env={"CI": "1"},
                timeout_seconds=120,
                on_failure=OnFailureSpec(action=FailurePolicy.ABORT),
            ),
        )

    def test_step_facade_resolves_run_shorthand(self) -> None:
        """Step.load and Step.resolve expand shorthand run directly on facade."""
        raw = {"id": "test", "run": "pytest"}
        step_obj = Step.load(raw)
        assert step_obj is not None
        resolved = step_obj.resolve()
        assert resolved is not None
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "pytest"


class StepResolutionTests:
    """Unit tests verifying step inheritance and field overlay behavior."""

    def test_resolve_step_uses_inherits_and_overlays_explicit_fields_only(self, tmp_path: Path) -> None:
        """Inherited step overlays explicitly set fields while preserving base definition defaults."""
        steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
        steps_dir.mkdir(parents=True, exist_ok=True)
        base_yaml = (
            "id: base-step\n"
            "name: Base Step Name\n"
            "description: Base step description\n"
            "type: command\n"
            "command: echo base\n"
            "env:\n"
            "  BASE_VAR: base\n"
            "  SHARED_VAR: base_val\n"
            "timeout_seconds: 60\n"
            "on_failure: abort\n"
        )
        (steps_dir / "base-step.yaml").write_text(base_yaml, encoding="utf-8")

        overriding = {
            "id": "derived-step",
            "uses": "base-step",
            "name": "Derived Step Name",
            "env": {"OVERRIDE_VAR": "derived", "SHARED_VAR": "overridden"},
            "timeout_seconds": 300,
        }

        resolved = resolve_step_definition(overriding, path=tmp_path)

        assert_model_equal(
            resolved,
            StepDefinition(
                id="derived-step",
                name="Derived Step Name",
                description="Base step description",
                type=StepType.COMMAND,
                command="echo base",
                env={"BASE_VAR": "base", "SHARED_VAR": "overridden", "OVERRIDE_VAR": "derived"},
                timeout_seconds=300,
                on_failure=OnFailureSpec(action=FailurePolicy.ABORT),
            ),
        )

    def test_step_load_by_name_via_catalog(self, tmp_path: Path) -> None:
        """Step.load_by_name resolves indexed step from workspace catalog."""
        steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
        steps_dir.mkdir(parents=True, exist_ok=True)
        (steps_dir / "catalog-step.yaml").write_text("id: catalog-step\nrun: echo hello\n", encoding="utf-8")

        loaded = Step.load_by_name("catalog-step", path=tmp_path)
        assert loaded is not None
        assert loaded.instance.id == "catalog-step"
        assert loaded.instance.run == "echo hello"

    def test_step_load_from_instance(self) -> None:
        """Step.load wraps an existing StepDefinition instance."""
        inst = StepDefinition(id="inst", type=StepType.COMMAND, command="echo 1")
        loaded = Step.load(inst)
        assert loaded is not None
        assert loaded.instance.id == "inst"

    def test_step_load_invalid_dictionary_returns_none(self) -> None:
        """Step.load returns None on schema-invalid dictionary payloads."""
        assert Step.load({"unexpected": "key", "id": 123}) is None

    def test_step_init_without_args_raises_value_error(self) -> None:
        """Step initialization requires either an instance or definition."""
        with pytest.raises(ValueError, match="requires an instance or definition"):
            Step()

    def test_step_load_by_path(self, tmp_path: Path) -> None:
        """Step.load_by_path loads valid YAML file and returns None for missing path."""
        step_file = tmp_path / "custom.yaml"
        step_file.write_text("id: custom\ntype: command\ncommand: echo hi\n", encoding="utf-8")

        loaded = Step.load_by_path(step_file)
        assert loaded is not None
        assert loaded.instance.id == "custom"

        missing = Step.load_by_path(tmp_path / "nonexistent.yaml")
        assert missing is None

    def test_step_resolve_concrete_type_returns_self_instance(self) -> None:
        """Step with explicit type resolves to its own instance unchanged."""
        inst = StepDefinition(id="c", type=StepType.COMMAND, command="ls")
        step_obj = Step(instance=inst)
        assert step_obj.resolve() == inst

    def test_resolve_step_recursive_uses(self, tmp_path: Path) -> None:
        """Step inheriting from another shorthand step resolves recursively."""
        steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
        steps_dir.mkdir(parents=True, exist_ok=True)
        (steps_dir / "root.yaml").write_text("id: root\nrun: echo root\n", encoding="utf-8")
        (steps_dir / "mid.yaml").write_text("id: mid\nuses: root\nname: Mid Name\n", encoding="utf-8")

        leaf = {"id": "leaf", "uses": "mid", "name": "Leaf Name"}
        resolved = resolve_step_definition(leaf, path=tmp_path)
        assert resolved.id == "leaf"
        assert resolved.name == "Leaf Name"
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "echo root"

    def test_resolve_step_without_path_raises_validation_error(self) -> None:
        """Resolving a 'uses' step without path raises StepValidationError."""
        with pytest.raises(StepValidationError, match="without workspace path"):
            resolve_step_definition({"id": "d", "uses": "base"})

    def test_resolve_step_missing_shorthand_or_type_raises_validation_error(self) -> None:
        """Step without run, uses, or type raises StepValidationError."""
        with pytest.raises(StepValidationError, match="must specify one of 'run', 'uses', or 'type'"):
            resolve_step_definition(StepDefinition.model_construct(id="empty"))

    def test_resolve_step_malformed_dict_raises_validation_error(self) -> None:
        """Malformed dictionary passed to resolve_step_definition raises StepValidationError."""
        with pytest.raises(StepValidationError, match="Step validation failed"):
            resolve_step_definition({"id": "bad", "timeout_seconds": "invalid-int"})
