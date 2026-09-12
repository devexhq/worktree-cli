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


class CatalogResolveTests:
    """Unit tests for Catalog resolution logic across blueprints and steps."""

    def test_catalog_cwd_is_resolved(self, fs: FileSystem) -> None:
        catalog = Catalog(fs.base_path)
        assert catalog.cwd == fs.base_path.resolve()

    def test_resolve_loads_blueprint_raw_without_kind(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/lint.yml", "name: lint\ndescription: Run linter\nsteps: []\n")
        result = Catalog(fs.base_path).resolve("lint", item_type=CatalogItemType.BLUEPRINT)

        assert result.ok
        assert result.status == CatalogResolveStatus.OK
        assert result.raw == {"name": "lint", "description": "Run linter", "steps": []}
        assert result.record is not None
        assert result.record.item_type == CatalogItemType.BLUEPRINT
        assert result.record.key == "lint"
        assert result.errors == []

    def test_resolve_loads_blueprint_by_sha(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/ship.yml", "name: ship\nsteps: []\n")
        catalog = Catalog(fs.base_path)
        listed = catalog.list(kind=CatalogItemType.BLUEPRINT)

        result = catalog.resolve(listed.items[0].sha, item_type=CatalogItemType.BLUEPRINT)

        assert result.ok
        assert result.record is not None
        assert result.record.item_type == CatalogItemType.BLUEPRINT
        assert result.raw == {"name": "ship", "steps": []}

    def test_resolve_step_loads_step_yaml(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\naction: run\n")
        result = Catalog(fs.base_path).resolve("git-check", item_type=CatalogItemType.STEP)

        assert result.ok
        assert result.record is not None
        assert result.record.item_type == CatalogItemType.STEP
        assert result.raw == {"name": "git-check", "action": "run"}

    def test_resolve_unknown_blueprint_is_not_found(self, fs: FileSystem) -> None:
        result = Catalog(fs.base_path).resolve("missing-item", item_type=CatalogItemType.BLUEPRINT)

        assert not result.ok
        assert result.status == CatalogResolveStatus.NOT_FOUND
        assert result.record is None
        assert result.raw is None
        assert result.errors == ["Catalog blueprint 'missing-item' not found."]

    def test_resolve_unknown_step_is_not_found(self, fs: FileSystem) -> None:
        result = Catalog(fs.base_path).resolve("missing-step", item_type=CatalogItemType.STEP)

        assert result.status == CatalogResolveStatus.NOT_FOUND
        assert result.errors == ["Catalog blueprint 'missing-step' not found."]

    def test_resolve_malformed_yaml_is_load_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/bad.yml", "invalid: yaml: [")
        result = Catalog(fs.base_path).resolve("bad", item_type=CatalogItemType.BLUEPRINT)

        assert result.status == CatalogResolveStatus.LOAD_ERROR
        assert result.raw is None
        assert result.record is not None
        assert result.record.key == "bad"
        assert result.errors

    def test_resolve_non_object_yaml_is_load_error(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/list.yml", "- just\n- a list\n")
        result = Catalog(fs.base_path).resolve("list", item_type=CatalogItemType.BLUEPRINT)

        assert result.status == CatalogResolveStatus.LOAD_ERROR
        assert result.raw is None
        assert any("invalid or non-object" in error for error in result.errors)


class CatalogListTests:
    """Unit tests for listing catalog items and packaged templates."""

    def test_list_returns_all_records(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/ship.yml", "name: ship\n")
        fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\n")
        result = Catalog(fs.base_path).list()
        records = result.items

        assert {record.item_type for record in records} == {
            CatalogItemType.BLUEPRINT,
            CatalogItemType.STEP,
        }
        assert len(records) == 2

    def test_list_filters_by_kind(self, fs: FileSystem) -> None:
        fs.write_file(".worktree/catalog/blueprints/ship.yml", "name: ship\n")
        fs.write_file(".worktree/catalog/steps/git-check.yml", "name: git-check\n")
        result = Catalog(fs.base_path).list(kind=CatalogItemType.BLUEPRINT)

        assert len(result.items) == 1
        assert result.items[0].name == "ship"

    def test_list_empty_catalog_returns_empty_list(self, fs: FileSystem) -> None:
        assert Catalog(fs.base_path).list().items == []

    def test_list_invalid_kind_returns_error(self, fs: FileSystem) -> None:
        result = Catalog(fs.base_path).list(kind="invalid_type")
        assert not result.ok
        assert "Invalid --type argument" in result.errors[0]

    def test_list_packaged_template_defaults(self) -> None:
        from worktree.core.catalog.services.inventory import list_packaged_template_defaults

        defaults = list_packaged_template_defaults()

        assert defaults == [
            ("blueprint", "blueprints/default.yml"),
            ("step", "steps/default.yml"),
        ]

    def test_find_packaged_templates_default(self) -> None:
        from worktree.core.catalog.services.inventory import find_packaged_templates

        found = find_packaged_templates("default")

        assert [path for path, _ in found] == [
            "blueprints/default.yml",
            "steps/default.yml",
        ]

    def test_find_packaged_templates_missing(self) -> None:
        from worktree.core.catalog.services.inventory import find_packaged_templates

        found = find_packaged_templates("nonexistent_template_xyz")
        assert found == []


class CatalogFileOperationsTests:
    """Unit tests for saving, writing, reading, and parsing catalog YAML files."""

    def test_save_writes_yaml_and_returns_record(self, fs: FileSystem) -> None:
        record = Catalog(fs.base_path).save(
            "lint",
            {"name": "lint", "description": "Run linter"},
            item_type=CatalogItemType.BLUEPRINT,
        )
        path = fs.base_path / ".worktree" / "catalog" / "blueprints" / "lint.yml"

        assert record.item_type == CatalogItemType.BLUEPRINT
        assert record.key == "lint"
        assert path.is_file()
        assert "kind:" not in path.read_text(encoding="utf-8")

        result = Catalog(fs.base_path).resolve("lint", item_type=CatalogItemType.BLUEPRINT)
        assert result.ok
        assert result.raw == {"name": "lint", "description": "Run linter"}

    def test_save_overwrites_existing_file(self, fs: FileSystem) -> None:
        catalog = Catalog(fs.base_path)
        catalog.save("lint", {"name": "lint", "version": 1}, item_type=CatalogItemType.BLUEPRINT)
        catalog.save("lint", {"name": "lint", "version": 2}, item_type=CatalogItemType.BLUEPRINT)
        result = catalog.resolve("lint", item_type=CatalogItemType.BLUEPRINT)

        assert result.raw == {"name": "lint", "version": 2}

    def test_save_nested_name_creates_parent_directories(self, fs: FileSystem) -> None:
        record = Catalog(fs.base_path).save(
            "wt/ai-code-patcher",
            {"name": "ai-code-patcher", "action": "run"},
            item_type=CatalogItemType.STEP,
        )
        path = fs.base_path / ".worktree" / "catalog" / "steps" / "wt" / "ai-code-patcher.yml"

        assert path.is_file()
        assert record.path.as_posix() == "steps/wt/ai-code-patcher.yml"
        assert record.key == "wt/ai-code-patcher"

        result = Catalog(fs.base_path).resolve("wt/ai-code-patcher", item_type=CatalogItemType.STEP)
        assert result.ok

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("lint.yaml", id="yaml_extension"),
            pytest.param("lint.yml", id="yml_extension"),
        ],
    )
    def test_save_strips_yaml_suffix(self, fs: FileSystem, name: str) -> None:
        Catalog(fs.base_path).save(name, {"name": "lint"}, item_type=CatalogItemType.BLUEPRINT)
        assert (fs.base_path / ".worktree" / "catalog" / "blueprints" / "lint.yml").is_file()

    def test_save_invalid_item_type_raises(self, fs: FileSystem) -> None:
        with pytest.raises(ValueError, match="Allowed choices"):
            Catalog(fs.base_path).save("lint", {"name": "lint"}, item_type="invalid_type")

    def test_save_os_error_raises_write_error(self, fs: FileSystem) -> None:
        catalog = Catalog(fs.base_path)
        with patch(
            "worktree.core.catalog.catalog.Filesystem.atomic_write_text",
            side_effect=OSError("permission denied"),
        ):
            with pytest.raises(CatalogWriteError, match="permission denied"):
                catalog.save("lint", {"name": "lint"}, item_type=CatalogItemType.BLUEPRINT)

    def test_read_yaml_returns_object(self, fs: FileSystem) -> None:
        path = fs.write_file(".worktree/catalog/blueprints/lint.yml", "name: lint\nsteps: []\n")
        assert Catalog.read_yaml(path) == {"name": "lint", "steps": []}

    def test_read_yaml_missing_path_raises(self, fs: FileSystem) -> None:
        missing = fs.base_path / "missing.yml"
        with pytest.raises(CatalogFileNotFoundError, match="not found"):
            Catalog.read_yaml(missing)

    def test_read_yaml_non_object_raises(self, fs: FileSystem) -> None:
        path = fs.write_file("scalar.yml", "just-a-string\n")
        with pytest.raises(CatalogYamlError, match="non-object"):
            Catalog.read_yaml(path)

    def test_record_for_rel_path_uses_get_by_path(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        catalog = Catalog(fs.base_path)
        record = catalog.save("lint", {"name": "lint"}, item_type=CatalogItemType.BLUEPRINT)

        def _forbidden_list(*_args: object, **_kwargs: object) -> list[object]:
            raise AssertionError("CatalogRepository.list should not be called by _record_for_rel_path")

        monkeypatch.setattr(catalog.db, "list", _forbidden_list)
        found = catalog._record_for_rel_path(Path("blueprints/lint.yml"))

        assert found is not None
        assert found.sha == record.sha

    def test_catalog_module_does_not_import_higher_domains(self) -> None:
        import worktree.core.catalog.catalog as catalog_mod

        source = Path(catalog_mod.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "worktree.core.step",
            "worktree.core.blueprint",
            "worktree.core.engine",
        ):
            assert f"import {forbidden}" not in source
            assert f"from {forbidden}" not in source
