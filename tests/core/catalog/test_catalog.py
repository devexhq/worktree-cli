"""Unit tests for the Catalog inventory facade."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers import FileSystem
from worktree.core.catalog import (
    Catalog,
    CatalogFileNotFoundError,
    CatalogResolveStatus,
    CatalogWriteError,
    CatalogYamlError,
)
from worktree.core.db import CatalogItemType


def test_catalog_cwd_is_resolved(fs: FileSystem) -> None:
    catalog = Catalog(fs.base_path)
    assert catalog.cwd == fs.base_path.resolve()


def test_resolve_loads_task_raw_without_kind(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\ndescription: Run linter\nsteps: []\n")
    result = Catalog(fs.base_path).resolve("lint")

    assert result.ok
    assert result.status == CatalogResolveStatus.OK
    assert result.raw == {"name": "lint", "description": "Run linter", "steps": []}
    assert result.raw is not None
    assert "kind" not in result.raw
    assert result.record is not None
    assert result.record.item_type == CatalogItemType.TASK
    assert result.errors == []


def test_resolve_loads_workflow_by_sha(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/workflows/ship.yml", "name: ship\nsteps: []\n")
    catalog = Catalog(fs.base_path)
    listed = catalog.list(kind="workflow")
    result = catalog.resolve(listed[0].sha)

    assert result.ok
    assert result.record is not None
    assert result.record.item_type == CatalogItemType.WORKFLOW
    assert result.raw == {"name": "ship", "steps": []}


def test_resolve_step_loads_step_yaml(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\naction: run\n")
    result = Catalog(fs.base_path).resolve_step("git-check")

    assert result.ok
    assert result.record is not None
    assert result.record.item_type == CatalogItemType.STEP
    assert result.raw == {"name": "git-check", "action": "run"}


def test_resolve_unknown_name_is_not_found(fs: FileSystem) -> None:
    result = Catalog(fs.base_path).resolve("missing-item")

    assert not result.ok
    assert result.status == CatalogResolveStatus.NOT_FOUND
    assert result.record is None
    assert result.raw is None
    assert result.errors == ["Catalog blueprint 'missing-item' not found."]


def test_resolve_step_unknown_name_is_not_found(fs: FileSystem) -> None:
    result = Catalog(fs.base_path).resolve_step("missing-step")

    assert result.status == CatalogResolveStatus.NOT_FOUND
    assert result.errors == ["Catalog blueprint 'missing-step' not found."]


def test_resolve_ignores_step_only_name(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\naction: run\n")
    catalog = Catalog(fs.base_path)
    step = catalog.list(kind="step")[0]
    by_name = catalog.resolve("git-check")
    by_sha = catalog.resolve(step.sha)

    assert by_name.status == CatalogResolveStatus.NOT_FOUND
    assert by_name.errors == ["Catalog blueprint 'git-check' not found."]
    assert by_sha.status == CatalogResolveStatus.NOT_FOUND


def test_resolve_step_ignores_task_name(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\nsteps: []\n")
    result = Catalog(fs.base_path).resolve_step("lint")

    assert result.status == CatalogResolveStatus.NOT_FOUND


def test_resolve_duplicate_task_and_workflow_names_warns(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/workflows/shared.yml", "name: shared\nsteps: []\n")
    fs.write_file(".worktree/catalog/tasks/shared.yml", "name: shared\nsteps: []\n")
    result = Catalog(fs.base_path).resolve("shared")

    assert result.ok
    assert result.record is not None
    assert result.record.path.as_posix() == "tasks/shared.yml"
    assert len(result.matches) == 2
    assert len(result.warnings) == 1
    assert "Duplicate catalog name 'shared'" in result.warnings[0]
    assert "tasks/shared.yml" in result.warnings[0]
    assert "workflows/shared.yml" in result.warnings[0]


def test_resolve_malformed_yaml_is_load_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/bad.yml", "invalid: yaml: [")
    result = Catalog(fs.base_path).resolve("bad")

    assert result.status == CatalogResolveStatus.LOAD_ERROR
    assert result.raw is None
    assert result.record is not None
    assert len(result.errors) > 0


def test_resolve_non_object_yaml_is_load_error(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/tasks/list.yml", "- just\n- a list\n")
    result = Catalog(fs.base_path).resolve("list")

    assert result.status == CatalogResolveStatus.LOAD_ERROR
    assert result.raw is None
    assert any("invalid or non-object" in error for error in result.errors)


def test_list_returns_all_records(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/workflows/ship.yml", "name: ship\n")
    fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\n")
    fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\n")
    records = Catalog(fs.base_path).list()

    assert {record.item_type for record in records} == {
        CatalogItemType.WORKFLOW,
        CatalogItemType.TASK,
        CatalogItemType.STEP,
    }
    assert len(records) == 3


def test_list_filters_by_kind(fs: FileSystem) -> None:
    fs.write_file(".worktree/catalog/workflows/ship.yml", "name: ship\n")
    fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\n")
    records = Catalog(fs.base_path).list(kind=CatalogItemType.TASK)

    assert len(records) == 1
    assert records[0].name == "lint"


def test_list_empty_catalog_returns_empty_list(fs: FileSystem) -> None:
    assert Catalog(fs.base_path).list() == []


def test_list_invalid_kind_raises(fs: FileSystem) -> None:
    with pytest.raises(ValueError, match="Allowed choices"):
        Catalog(fs.base_path).list(kind="invalid_type")


def test_save_writes_yaml_and_returns_record(fs: FileSystem) -> None:
    record = Catalog(fs.base_path).save(
        "lint",
        {"name": "lint", "description": "Run linter"},
        item_type=CatalogItemType.TASK,
    )
    path = fs.base_path / ".worktree" / "catalog" / "tasks" / "lint.yml"

    assert record.item_type == CatalogItemType.TASK
    assert path.is_file()
    assert "kind:" not in path.read_text(encoding="utf-8")
    result = Catalog(fs.base_path).resolve("lint")
    assert result.ok
    assert result.raw == {"name": "lint", "description": "Run linter"}


def test_save_overwrites_existing_file(fs: FileSystem) -> None:
    catalog = Catalog(fs.base_path)
    catalog.save("lint", {"name": "lint", "version": 1}, item_type="task")
    catalog.save("lint", {"name": "lint", "version": 2}, item_type="task")
    result = catalog.resolve("lint")

    assert result.raw == {"name": "lint", "version": 2}


def test_save_nested_name_creates_parent_directories(fs: FileSystem) -> None:
    record = Catalog(fs.base_path).save(
        "wt/ai-code-patcher",
        {"name": "ai-code-patcher", "action": "run"},
        item_type=CatalogItemType.STEP,
    )
    path = fs.base_path / ".worktree" / "catalog" / "steps" / "wt" / "ai-code-patcher.yml"

    assert path.is_file()
    assert record.path.as_posix() == "steps/wt/ai-code-patcher.yml"
    result = Catalog(fs.base_path).resolve_step("ai-code-patcher")
    assert result.ok


@pytest.mark.parametrize("name", ["lint.yaml", "lint.yml"])
def test_save_strips_yaml_suffix(fs: FileSystem, name: str) -> None:
    Catalog(fs.base_path).save(name, {"name": "lint"}, item_type=CatalogItemType.TASK)
    assert (fs.base_path / ".worktree" / "catalog" / "tasks" / "lint.yml").is_file()


def test_save_invalid_item_type_raises(fs: FileSystem) -> None:
    with pytest.raises(ValueError, match="Allowed choices"):
        Catalog(fs.base_path).save("lint", {"name": "lint"}, item_type="invalid_type")


def test_save_os_error_raises_write_error(fs: FileSystem) -> None:
    catalog = Catalog(fs.base_path)
    with patch("worktree.core.catalog.catalog.atomic_write_text", side_effect=OSError("permission denied")):
        with pytest.raises(CatalogWriteError, match="permission denied"):
            catalog.save("lint", {"name": "lint"}, item_type=CatalogItemType.TASK)


def test_read_yaml_returns_object(fs: FileSystem) -> None:
    path = fs.write_file(".worktree/catalog/tasks/lint.yml", "name: lint\nsteps: []\n")
    assert Catalog.read_yaml(path) == {"name": "lint", "steps": []}


def test_read_yaml_missing_path_raises(fs: FileSystem) -> None:
    missing = fs.base_path / "missing.yml"
    with pytest.raises(CatalogFileNotFoundError, match="not found"):
        Catalog.read_yaml(missing)


def test_read_yaml_non_object_raises(fs: FileSystem) -> None:
    path = fs.write_file("scalar.yml", "just-a-string\n")
    with pytest.raises(CatalogYamlError, match="non-object"):
        Catalog.read_yaml(path)


def test_catalog_module_does_not_import_higher_domains() -> None:
    import worktree.core.catalog.catalog as catalog_mod

    source = Path(catalog_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "worktree.core.step",
        "worktree.core.blueprint",
        "worktree.core.engine",
        "worktree.core.task",
        "worktree.core.workflows",
    ):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source


def test_list_packaged_template_defaults() -> None:
    from worktree.core.catalog.services.inventory import list_packaged_template_defaults

    defaults = list_packaged_template_defaults()
    assert len(defaults) == 3
    types = [t for t, _ in defaults]
    assert "workflow" in types
    assert "task" in types
    assert "step" in types


def test_find_packaged_templates_default() -> None:
    from worktree.core.catalog.services.inventory import find_packaged_templates

    found = find_packaged_templates("default")
    assert len(found) == 3
    paths = [p for p, _ in found]
    assert "workflows/default.yml" in paths
    assert "tasks/default.yml" in paths
    assert "steps/default.yml" in paths


def test_find_packaged_templates_missing() -> None:
    from worktree.core.catalog.services.inventory import find_packaged_templates

    found = find_packaged_templates("nonexistent_template_xyz")
    assert found == []
