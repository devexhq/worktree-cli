"""Tests for the Blueprint domain facade."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def test_blueprint_facade_dump_and_resolve_inputs() -> None:
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


def test_blueprint_facade_load_uses_catalog_key_and_path(fs: FileSystem) -> None:
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
