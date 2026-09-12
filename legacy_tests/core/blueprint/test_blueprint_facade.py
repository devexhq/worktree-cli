"""Tests for the Blueprint domain facade."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.blueprint import (
    Blueprint,
    BlueprintDefinition,
    BlueprintLoadError,
    BlueprintNotFoundError,
)
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType
from worktree.core.inputs import InputType, ParameterInput
from worktree.core.step import LoopStepBlock, StepDefinition


def _blueprint_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "lint",
        "description": "Run linter",
        "steps": [{"id": "ruff", "run": "ruff check ."}],
    }
    payload.update(overrides)
    return payload


class BlueprintHandleTests:
    """Unit tests for in-memory Blueprint handle behavior."""

    def test_construct_from_definition_keeps_live_document_and_stable_key(self) -> None:
        definition = BlueprintDefinition.model_validate(_blueprint_payload())
        blueprint = Blueprint(definition)

        definition.name = "mutated"

        assert blueprint.name == "mutated"
        assert blueprint.key == "lint"
        assert Blueprint.spec is BlueprintDefinition

    def test_use_sandbox_property_reads_document(self) -> None:
        blueprint = Blueprint(BlueprintDefinition.model_validate(_blueprint_payload(use_sandbox=False)))

        assert blueprint.use_sandbox is False

    def test_resolve_inputs_uses_blueprint_declarations(self) -> None:
        blueprint = Blueprint(
            BlueprintDefinition.model_validate(
                {
                    "name": "commit",
                    "inputs": {
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
                }
            )
        )

        result = blueprint.resolve_inputs(["-m", "ship it"])

        assert result.ok
        assert result.values == {"message": "ship it", "allow_empty": False}

    def test_inspect_properties_are_live(self) -> None:
        definition = BlueprintDefinition.model_validate(
            {
                "name": "lint",
                "inputs": {},
                "steps": [{"id": "ruff", "run": "ruff check ."}],
            }
        )
        blueprint = Blueprint(definition, key="bp/lint")
        definition.steps.clear()

        assert blueprint.steps == []
        assert blueprint.inputs is definition.inputs
        assert blueprint.path is None

    def test_dump_returns_definition_payload(self, fs: FileSystem) -> None:
        definition = BlueprintDefinition.model_validate({"name": "ship"})

        assert Blueprint(definition, key="ship").dump() == definition.model_dump(mode="json")
        assert list(fs.base_path.iterdir()) == []

    def test_handle_module_does_not_import_engine_types(self) -> None:
        source = Path("src/worktree/core/blueprint/facade.py").read_text(encoding="utf-8")
        models = Path("src/worktree/core/blueprint/models.py").read_text(encoding="utf-8")

        assert "worktree.core.engine" not in source
        assert "worktree.core.catalog" not in models


class BlueprintLoadCatalogTests:
    """Unit tests for loading blueprints from the catalog by key."""

    def test_load_blueprint_from_catalog_key(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/lint.yml", _blueprint_payload())

        blueprint = Blueprint.load("lint", catalog=Catalog(fs.base_path))

        assert blueprint.name == "lint"
        assert blueprint.key == "lint"
        assert blueprint.path == Path("blueprints/lint.yml")
        assert len(blueprint.steps) == 1
        assert isinstance(blueprint.steps[0], StepDefinition)

    def test_load_nested_key_defaults_name_from_catalog_key(self, fs: FileSystem) -> None:
        fs.write_file(
            ".worktree/catalog/blueprints/wt/fix-tests.yml",
            {"steps": [{"id": "pytest", "run": "pytest -q"}]},
        )

        blueprint = Blueprint.load("wt/fix-tests", catalog=Catalog(fs.base_path))

        assert blueprint.name == "wt/fix-tests"
        assert blueprint.key == "wt/fix-tests"
        assert blueprint.path == Path("blueprints/wt/fix-tests.yml")

    def test_load_unknown_key_raises_not_found(self, fs: FileSystem) -> None:
        with pytest.raises(BlueprintNotFoundError, match=r"Catalog blueprint 'missing-blueprint' not found\."):
            Blueprint.load("missing-blueprint", catalog=Catalog(fs.base_path))

    def test_load_malformed_catalog_yaml_raises_load_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/bad.yml", "invalid: yaml: [")

        with pytest.raises(BlueprintLoadError, match="Failed to load catalog blueprint"):
            Blueprint.load("bad", catalog=Catalog(fs.base_path))

    def test_load_non_object_catalog_yaml_raises_load_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/list.yml", "- just\n- a list\n")

        with pytest.raises(BlueprintLoadError, match="invalid or non-object YAML content"):
            Blueprint.load("list", catalog=Catalog(fs.base_path))

    def test_load_invalid_document_raises_load_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/broken.yml", {"name": ""})

        with pytest.raises(BlueprintLoadError, match="Blueprint definition validation failed"):
            Blueprint.load("broken", catalog=Catalog(fs.base_path))

    def test_load_blueprint_with_loop_step_succeeds(self, fs: FileSystem) -> None:
        fs.write_file(
            ".worktree/catalog/blueprints/ship.yml",
            {
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
            },
        )

        blueprint = Blueprint.load("ship", catalog=Catalog(fs.base_path))

        assert any(isinstance(step, LoopStepBlock) for step in blueprint.steps)


class BlueprintFacadeLifecycleTests:
    """Tests for Blueprint domain facade dump and catalog loading."""

    def test_blueprint_facade_dump_and_resolve_inputs(self) -> None:
        blueprint = Blueprint(
            BlueprintDefinition.model_validate(
                {
                    "name": "lint-all",
                    "description": "Lint the whole repo",
                    "use_sandbox": False,
                    "steps": [{"id": "run-ruff", "run": "ruff check ."}],
                    "inputs": {"fix": {"type": "boolean", "default": False, "aliases": ["--fix"]}},
                }
            ),
            key="lint-all",
        )

        assert blueprint.name == "lint-all"
        assert blueprint.key == "lint-all"
        assert blueprint.use_sandbox is False
        assert len(blueprint.steps) == 1
        assert "fix" in blueprint.inputs
        assert blueprint.dump()["name"] == "lint-all"

        result = blueprint.resolve_inputs(["--fix=true"])
        assert result.ok
        assert result.values == {"fix": True}

    def test_blueprint_facade_load_uses_catalog_key_and_path(self, fs: FileSystem) -> None:
        catalog = Catalog(fs.base_path)
        catalog.save(
            "wt/build",
            {
                "version": "1.0",
                "steps": [{"id": "build-step", "run": "cargo build"}],
            },
            item_type=CatalogItemType.BLUEPRINT,
        )

        blueprint = Blueprint.load("wt/build", catalog=catalog)

        assert blueprint.name == "wt/build"
        assert blueprint.key == "wt/build"
        assert blueprint.path == Path("blueprints/wt/build.yml")
