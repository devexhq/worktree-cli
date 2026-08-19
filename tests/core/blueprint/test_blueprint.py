"""Unit tests for the Blueprint load/inspect handle."""

from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.blueprint import (
    Blueprint,
    BlueprintDefinition,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintValidationError,
)
from worktree.core.catalog import Catalog
from worktree.core.inputs import InputType, ParameterInput
from worktree.core.step import LoopStepBlock, StepDefinition


def _task_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "lint",
        "description": "Run linter",
        "steps": [{"id": "ruff", "run": "ruff check ."}],
    }
    payload.update(overrides)
    return payload


def _workflow_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "ship",
        "steps": [
            {"id": "ruff", "run": "ruff check ."},
            {
                "id": "retry",
                "type": "loop",
                "until": ["steps.unit.exit_code == 0"],
                "do": [{"id": "unit", "run": "pytest"}],
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_construct_from_definition_does_not_copy() -> None:
    definition = BlueprintDefinition(kind=BlueprintKind.TASK, name="lint")
    blueprint = Blueprint(definition)

    definition.name = "mutated"

    assert blueprint.name == "mutated"
    assert blueprint.kind is BlueprintKind.TASK
    assert Blueprint.spec is BlueprintDefinition


def test_use_sandbox_property_reads_document() -> None:
    blueprint = Blueprint(BlueprintDefinition(kind=BlueprintKind.TASK, name="lint", use_sandbox=False))

    assert blueprint.use_sandbox is False


def test_load_task_from_catalog_name(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/lint.yml", _task_payload())
    blueprint = Blueprint.load("lint", catalog=Catalog(fs.base_path))

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.name == "lint"
    assert len(blueprint.steps) == 1
    assert isinstance(blueprint.steps[0], StepDefinition)
    assert blueprint.dump()["kind"] == "task"
    raw = Catalog(fs.base_path).resolve("lint").raw
    assert raw is not None
    assert "kind" not in raw


def test_load_workflow_from_catalog_sha(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/workflows/ship.yml", _workflow_payload())
    catalog = Catalog(fs.base_path)
    sha = catalog.list(kind="workflow")[0].sha
    blueprint = Blueprint.load(sha, catalog=catalog)

    assert blueprint.kind is BlueprintKind.WORKFLOW
    assert blueprint.name == "ship"
    assert any(isinstance(step, LoopStepBlock) for step in blueprint.steps)


def test_load_uses_process_cwd_when_catalog_omitted(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    fs.write_file(".worktree/catalog/tasks/lint.yml", _task_payload())
    monkeypatch.chdir(fs.base_path)

    blueprint = Blueprint.load("lint")

    assert blueprint.name == "lint"
    assert blueprint.kind is BlueprintKind.TASK


def test_load_unknown_name_raises_not_found(fs: FileSystem) -> None:
    with pytest.raises(BlueprintNotFoundError, match=r"Blueprint 'missing-task' not found in catalog\."):
        Blueprint.load("missing-task", catalog=Catalog(fs.base_path))


def test_load_step_only_name_raises_not_found(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/steps/git-check.yml", {"id": "git-check", "run": "git status"})
    with pytest.raises(BlueprintNotFoundError, match=r"Blueprint 'git-check' not found in catalog\."):
        Blueprint.load("git-check", catalog=Catalog(fs.base_path))


def test_load_malformed_catalog_yaml_raises_load_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/bad.yml", "invalid: yaml: [")
    with pytest.raises(BlueprintLoadError, match="Failed to load blueprint 'bad' from catalog"):
        Blueprint.load("bad", catalog=Catalog(fs.base_path))


def test_load_non_object_catalog_yaml_raises_load_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/list.yml", "- just\n- a list\n")
    with pytest.raises(BlueprintLoadError, match="Failed to load blueprint 'list' from catalog"):
        Blueprint.load("list", catalog=Catalog(fs.base_path))


def test_load_invalid_document_raises_validation_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/broken.yml", {"name": ""})
    with pytest.raises(BlueprintValidationError, match="kind='task'"):
        Blueprint.load("broken", catalog=Catalog(fs.base_path))


def test_load_task_with_loop_step_raises_validation_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/looped.yml", _workflow_payload(name="looped"))
    with pytest.raises(BlueprintValidationError, match="kind=task cannot contain loop steps"):
        Blueprint.load("looped", catalog=Catalog(fs.base_path))


def test_load_ignores_authored_yaml_kind(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/lint.yml", _task_payload(kind="workflow"))
    blueprint = Blueprint.load("lint", catalog=Catalog(fs.base_path))

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.dump()["kind"] == "task"


def test_from_path_task_folder(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/tasks/lint.yml", _task_payload())
    blueprint = Blueprint.from_path(path)

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.name == "lint"


def test_from_path_nested_workflow_folder(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/workflows/wt/fix-tests.yml", _workflow_payload(name="fix-tests"))
    blueprint = Blueprint.from_path(path)

    assert blueprint.kind is BlueprintKind.WORKFLOW
    assert blueprint.name == "fix-tests"


def test_from_path_closest_folder_wins(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/workflows/tasks/nested.yml", _task_payload(name="nested"))
    blueprint = Blueprint.from_path(path)

    assert blueprint.kind is BlueprintKind.TASK
    assert blueprint.name == "nested"


def test_from_path_missing_folder_context_does_not_read_file(fs: FileSystem) -> None:
    missing = fs.base_path / "foo.yml"
    with pytest.raises(
        BlueprintValidationError,
        match=r"Cannot infer blueprint kind from path '.*foo.yml'; expected a parent 'tasks/' or 'workflows/' segment\.",
    ):
        Blueprint.from_path(missing)
    assert not missing.exists()


def test_from_path_under_steps_fails_without_reading(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/steps/git-check.yml", "not: valid: yaml: [")
    with pytest.raises(BlueprintValidationError, match="expected a parent 'tasks/' or 'workflows/' segment"):
        Blueprint.from_path(path)


def test_from_path_missing_file_raises_load_error(fs: FileSystem) -> None:
    missing = fs.base_path / "tasks" / "gone.yml"
    missing.parent.mkdir(parents=True)
    with pytest.raises(BlueprintLoadError, match="Failed to load blueprint from"):
        Blueprint.from_path(missing)


def test_from_path_malformed_yaml_raises_load_error(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/tasks/bad.yml", "invalid: yaml: [")
    with pytest.raises(BlueprintLoadError, match="Failed to load blueprint from"):
        Blueprint.from_path(path)


def test_resolve_inputs_uses_blueprint_declarations() -> None:
    blueprint = Blueprint(
        BlueprintDefinition(
            kind=BlueprintKind.TASK,
            name="commit",
            inputs={
                "message": ParameterInput(
                    type=InputType.STRING,
                    required=True,
                    aliases=["-m"],
                ),
                "allow_empty": ParameterInput(
                    type=InputType.BOOLEAN,
                    default=False,
                ),
            },
        )
    )

    result = blueprint.resolve_inputs(["-m", "ship it"])

    assert result.ok
    assert result.values == {"message": "ship it", "allow_empty": False}


def test_inspect_properties_are_live() -> None:
    definition = BlueprintDefinition(
        kind=BlueprintKind.TASK,
        name="lint",
        inputs={},
        steps=[StepDefinition.model_validate({"id": "ruff", "run": "ruff check ."})],
    )
    blueprint = Blueprint(definition)
    definition.steps.clear()

    assert blueprint.steps == []
    assert blueprint.inputs is definition.inputs


def test_dump_includes_derived_kind_and_does_not_write(fs: FileSystem) -> None:
    definition = BlueprintDefinition(kind=BlueprintKind.WORKFLOW, name="ship")
    dumped = Blueprint(definition).dump()

    assert dumped["kind"] == "workflow"
    assert dumped["name"] == "ship"
    assert list(fs.base_path.iterdir()) == []


def test_handle_module_does_not_import_side_channel_types() -> None:
    source = Path("src/worktree/core/blueprint/services/blueprint.py").read_text(encoding="utf-8")
    models = Path("src/worktree/core/blueprint/models.py").read_text(encoding="utf-8")

    for forbidden in ("worktree.core.engine", "worktree.core.task", "worktree.core.workflows"):
        assert forbidden not in source
    assert "worktree.core.catalog" not in models
