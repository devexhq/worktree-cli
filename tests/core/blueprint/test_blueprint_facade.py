"""Tests for Blueprint domain facade."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintKind
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def test_blueprint_facade_from_dict_and_dump():
    data = {
        "name": "lint-all",
        "description": "Lint the whole repo",
        "use_sandbox": False,
        "steps": [{"id": "run-ruff", "run": "ruff check ."}],
        "inputs": {"fix": {"type": "boolean", "default": False, "aliases": ["--fix"]}},
    }
    bp = Blueprint.from_dict(data, BlueprintKind.TASK)
    assert bp.name == "lint-all"
    assert bp.kind == BlueprintKind.TASK
    assert not bp.use_sandbox
    assert len(bp.steps) == 1
    assert "fix" in bp.inputs

    dumped = bp.dump()
    assert dumped["name"] == "lint-all"
    assert dumped["kind"] == "task"

    res = bp.resolve_inputs(["--fix=true"])
    assert res.ok
    assert res.values == {"fix": True}


def test_blueprint_facade_load_and_from_path(fs: FileSystem):
    catalog = Catalog(fs.base_path)
    catalog.save(
        "build",
        {
            "name": "build",
            "version": "1.0",
            "steps": [{"id": "build-step", "run": "cargo build"}],
        },
        item_type=CatalogItemType.WORKFLOW,
    )

    bp = Blueprint.load("build", catalog=catalog)
    assert bp.name == "build"
    assert bp.kind == BlueprintKind.WORKFLOW

    path = fs.base_path / ".worktree" / "catalog" / "workflows" / "build.yml"
    bp_from_path = Blueprint.from_path(path)
    assert bp_from_path.name == "build"
    assert bp_from_path.kind == BlueprintKind.WORKFLOW
