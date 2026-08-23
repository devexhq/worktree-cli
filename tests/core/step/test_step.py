"""Unit tests for the Step class handle."""

from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.catalog import Catalog
from worktree.core.step import (
    Step,
    StepDefinition,
    StepNotFoundError,
    StepType,
    StepValidationError,
    execute_step,
)


def _command_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "echo-msg",
        "name": "echo-msg",
        "type": "command",
        "command": "echo '${{ inputs.msg }}'",
        "env": {"MSG": "${{ inputs.msg }}"},
    }
    payload.update(overrides)
    return payload


class StepHandleTests:
    """Unit tests for in-memory Step handle creation, execution, and boundary isolation."""

    def test_construct_from_definition_does_not_copy(self, fs: FileSystem) -> None:
        definition = StepDefinition(id="keep", type=StepType.COMMAND, command="echo keep")
        step = Step(definition)

        definition.command = "echo mutated"

        assert step.id == "keep"
        assert step.dump()["command"] == "echo mutated"
        assert Step.spec is StepDefinition

    def test_load_from_definition_does_not_revalidate_or_interpolate(self) -> None:
        definition = StepDefinition(
            id="echo-msg",
            type=StepType.COMMAND,
            command="echo '${{ inputs.msg }}'",
        )
        step = Step.load(definition)

        assert step.id == "echo-msg"
        assert step.dump()["command"] == "echo '${{ inputs.msg }}'"

    def test_load_from_dict_validates_without_interpolating(self) -> None:
        step = Step.load(_command_payload())

        dumped = step.dump()
        assert step.id == "echo-msg"
        assert dumped["command"] == "echo '${{ inputs.msg }}'"
        assert dumped["env"]["MSG"] == "${{ inputs.msg }}"

    def test_load_from_dict_missing_shape_raises_validation_error(self) -> None:
        with pytest.raises(StepValidationError, match="validation failed"):
            Step.load({"id": "broken"})

    def test_load_from_dict_invalid_field_type_raises_validation_error(self) -> None:
        with pytest.raises(StepValidationError, match="validation failed"):
            Step.load({"id": "broken", "type": "command", "command": 12})

    def test_dump_does_not_interpolate(self) -> None:
        step = Step.load(_command_payload())

        assert step.dump()["command"] == "echo '${{ inputs.msg }}'"
        assert step.dump()["prompt"] is None

    def test_execute_interpolates_inputs_and_leaves_handle_untouched(self, fs: FileSystem) -> None:
        step = Step.load(_command_payload())

        result = step.execute(fs.base_path, inputs={"msg": "hello-world"})

        assert result.ok
        assert "hello-world" in result.stdout
        assert step.dump()["command"] == "echo '${{ inputs.msg }}'"
        assert step.dump()["env"]["MSG"] == "${{ inputs.msg }}"

    def test_execute_with_empty_inputs_does_not_interpolate(self, fs: FileSystem) -> None:
        step = Step.load(_command_payload(command="echo '${{ inputs.msg }}'"))

        result = step.execute(fs.base_path, inputs={})

        assert result.ok
        assert "${{ inputs.msg }}" in result.stdout
        assert step.dump()["command"] == "echo '${{ inputs.msg }}'"

    def test_execute_missing_sandbox_matches_execute_step(self, fs: FileSystem) -> None:
        definition = StepDefinition(id="echo-msg", type=StepType.COMMAND, command="echo hi")
        step = Step(definition)
        missing = fs.base_path / "missing-sandbox"

        handle_result = step.execute(missing)
        runner_result = execute_step(definition, missing)

        assert handle_result.status == runner_result.status == "failed"
        assert handle_result.error_message == runner_result.error_message
        assert "does not exist or is not a directory" in (handle_result.error_message or "")

    def test_handle_module_does_not_import_side_channel_types(self) -> None:
        source = Path("src/worktree/core/step/step.py").read_text(encoding="utf-8")

        for forbidden in (
            "worktree.core.blueprint",
            "worktree.core.engine",
            "worktree.core.task",
            "worktree.core.workflows",
        ):
            assert forbidden not in source


class StepCatalogTests:
    """Unit tests for loading step definitions from catalog index and files."""

    def test_load_from_catalog_name(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/echo-msg.yml", _command_payload())
        step = Step.load("echo-msg", catalog=Catalog(fs.base_path))

        assert step.id == "echo-msg"
        assert step.dump()["command"] == "echo '${{ inputs.msg }}'"

    def test_load_from_catalog_sha(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/echo-msg.yml", _command_payload())
        catalog = Catalog(fs.base_path)
        sha = catalog.list(kind="step")[0].sha
        step = Step.load(sha, catalog=catalog)

        assert step.id == "echo-msg"

    def test_load_from_catalog_uses_process_cwd_when_omitted(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fs.write_file(".worktree/catalog/steps/echo-msg.yml", _command_payload())
        monkeypatch.chdir(fs.base_path)

        step = Step.load("echo-msg")

        assert step.id == "echo-msg"

    def test_load_unknown_catalog_name_raises_not_found(self, fs: FileSystem) -> None:
        with pytest.raises(StepNotFoundError, match=r"Step 'missing-step' not found in catalog\."):
            Step.load("missing-step", catalog=Catalog(fs.base_path))

    def test_load_task_only_name_raises_not_found(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\nsteps: []\n")
        with pytest.raises(StepNotFoundError, match=r"Step 'lint' not found in catalog\."):
            Step.load("lint", catalog=Catalog(fs.base_path))

    def test_load_malformed_catalog_yaml_raises_validation_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/bad.yml", "invalid: yaml: [")
        with pytest.raises(StepValidationError, match="Failed to load step 'bad' from catalog"):
            Step.load("bad", catalog=Catalog(fs.base_path))

    def test_load_non_object_catalog_yaml_raises_validation_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/list.yml", "- just\n- a list\n")
        with pytest.raises(StepValidationError, match="Failed to load step 'list' from catalog"):
            Step.load("list", catalog=Catalog(fs.base_path))

    def test_load_catalog_payload_that_fails_step_validation(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/incomplete.yml", "id: incomplete\nname: incomplete\n")
        with pytest.raises(StepValidationError, match="validation failed"):
            Step.load("incomplete", catalog=Catalog(fs.base_path))
