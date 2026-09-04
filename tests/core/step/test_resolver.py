"""Unit tests for resolve_step_definition (FR-6 uses/run resolution)."""

from __future__ import annotations

import pytest

from tests.helpers import FileSystem
from worktree.core.step import FailurePolicy, FailureSpec, StepDefinition, StepType, StepValidationError
from worktree.core.step.services.resolver import resolve_step_definition


class StepResolverTests:
    """Unit tests for resolving run shorthands, inline step types, and catalog uses references."""

    def test_resolve_run_step_synthesizes_command_step(self) -> None:
        step = StepDefinition(id="run-tests", run="pytest tests/ -q")

        resolved = resolve_step_definition(step)

        assert resolved.id == "run-tests"
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "pytest tests/ -q"
        assert resolved.uses is None
        assert resolved.run is None

    def test_resolve_inline_type_step_passes_through_unchanged(self) -> None:
        step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")

        resolved = resolve_step_definition(step)

        assert resolved is step

    def test_resolve_uses_step_loads_referenced_definition(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="lint", command="ruff check .")

        step = StepDefinition(id="lint-step", uses="lint")

        resolved = resolve_step_definition(step, path=fs.base_path)

        assert resolved.id == "lint-step"
        assert resolved.type == StepType.COMMAND
        assert resolved.command == "ruff check ."
        assert resolved.name == "run-lint"

    def test_resolve_uses_step_overrides_use_referencing_step_fields(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="base", name="base-name", command="echo base", timeout_seconds=30)

        step = StepDefinition(id="derived", uses="base", name="derived-name", timeout_seconds=90)

        resolved = resolve_step_definition(step, path=fs.base_path)

        assert resolved.name == "derived-name"
        assert resolved.timeout_seconds == 90
        assert resolved.command == "echo base"

    def test_resolve_uses_step_merges_on_failure_when_referencing_step_overrides(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="base", command="echo base", on_failure="continue")

        step = StepDefinition(id="derived", uses="base", on_failure=FailureSpec(action=FailurePolicy.ABORT))

        resolved = resolve_step_definition(step, path=fs.base_path)

        assert resolved.on_failure == FailureSpec(action=FailurePolicy.ABORT)

    def test_resolve_step_without_run_uses_or_type_raises(self) -> None:
        step = StepDefinition.model_construct(id="broken", uses=None, run=None, type=None)

        with pytest.raises(StepValidationError, match="Could not resolve step"):
            resolve_step_definition(step)
