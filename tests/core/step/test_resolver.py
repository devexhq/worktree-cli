"""Unit tests for resolve_step_definition (FR-6 uses/run resolution)."""

from pathlib import Path

import pytest

from getworktree.core.step import FailurePolicy, FailureSpec, StepDefinition, StepType, StepValidationError
from getworktree.core.step.services.resolver import resolve_step_definition


def test_resolve_run_step_synthesizes_command_step():
    step = StepDefinition(id="run-tests", run="pytest tests/ -q")

    resolved = resolve_step_definition(step)

    assert resolved.id == "run-tests"
    assert resolved.type == StepType.COMMAND
    assert resolved.command == "pytest tests/ -q"
    assert resolved.uses is None
    assert resolved.run is None


def test_resolve_inline_type_step_passes_through_unchanged():
    step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")

    resolved = resolve_step_definition(step)

    assert resolved is step


def test_resolve_uses_step_loads_referenced_definition(tmp_path: Path):
    steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "lint.yaml").write_text(
        "id: lint\nname: run-lint\ntype: command\ncommand: ruff check .\n",
        encoding="utf-8",
    )

    step = StepDefinition(id="lint-step", uses="lint")

    resolved = resolve_step_definition(step, cwd=tmp_path)

    assert resolved.id == "lint-step"
    assert resolved.type == StepType.COMMAND
    assert resolved.command == "ruff check ."
    assert resolved.name == "run-lint"


def test_resolve_uses_step_overrides_use_referencing_step_fields(tmp_path: Path):
    steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "base.yaml").write_text(
        "id: base\nname: base-name\ntype: command\ncommand: echo base\ntimeout_seconds: 30\n",
        encoding="utf-8",
    )

    step = StepDefinition(id="derived", uses="base", name="derived-name", timeout_seconds=90)

    resolved = resolve_step_definition(step, cwd=tmp_path)

    assert resolved.name == "derived-name"
    assert resolved.timeout_seconds == 90
    assert resolved.command == "echo base"


def test_resolve_uses_step_merges_on_failure_when_referencing_step_overrides(tmp_path: Path):
    steps_dir = tmp_path / ".worktree" / "catalog" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "base.yaml").write_text(
        "id: base\ntype: command\ncommand: echo base\non_failure: continue\n",
        encoding="utf-8",
    )

    step = StepDefinition(id="derived", uses="base", on_failure="abort")

    resolved = resolve_step_definition(step, cwd=tmp_path)

    assert resolved.on_failure == FailureSpec(action=FailurePolicy.ABORT)


def test_resolve_step_without_run_uses_or_type_raises():
    step = StepDefinition.model_construct(id="broken", uses=None, run=None, type=None)

    with pytest.raises(StepValidationError, match="Could not resolve step"):
        resolve_step_definition(step)
