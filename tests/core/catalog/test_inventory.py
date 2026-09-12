"""Tests for catalog inventory helper functions."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from tests.helpers import FileSystem
from worktree.common.filesystem import Filesystem
from worktree.common.models import DefinitionResolutionStatus
from worktree.core.catalog.services.inventory import (
    compute_catalog_sha,
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    ensure_catalog_dirs,
    get_catalog_item,
    scan_and_index_catalog,
)
from worktree.core.db import CatalogItemType, WorktreeDb


class SampleDefinition(BaseModel):
    name: str
    description: str = ""


class CatalogInventoryDirsAndChecksumTests:
    """Unit tests for catalog directory layout and content checksum calculation."""

    def test_ensure_catalog_dirs_creates_structure(self, fs: FileSystem) -> None:
        catalog_dir = ensure_catalog_dirs(fs.base_path)

        assert catalog_dir == fs.base_path / ".worktree" / "catalog"
        assert (catalog_dir / "blueprints").is_dir()
        assert (catalog_dir / "steps").is_dir()

    def test_compute_catalog_sha(self) -> None:
        sha, checksum = compute_catalog_sha(CatalogItemType.BLUEPRINT, "name: test\nsteps: []\n")

        assert sha.startswith("blueprint_")
        assert len(sha) == 17
        assert len(checksum) == 64
        assert sha == f"blueprint_{checksum[:7]}"
        assert checksum == Filesystem.compute_checksum("name: test\nsteps: []\n")

    def test_common_fs_checksum_and_delete(self, fs: FileSystem) -> None:
        content = "test text"
        checksum = Filesystem.compute_checksum(content)
        assert len(checksum) == 64

        test_path = fs.base_path / "sample.txt"
        fs.write_file("sample.txt", content)

        yaml_file = Filesystem.read_yaml_file(test_path)
        assert yaml_file.checksum == checksum
        assert yaml_file.file_size == len(content.encode("utf-8"))

        assert Filesystem().delete_file(test_path) is True
        assert not test_path.exists()
        assert Filesystem().delete_file(test_path) is False


class CatalogScannerAndIndexTests:
    """Unit tests for file system scanning and catalog index synchronization."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_scan_and_index_catalog(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/blueprints/feature-dev.yml", "name: Feature Dev Blueprint\nsteps: []\n")
        fs.write_file(".worktree/catalog/steps/git-check.yml", "name: Git Checkpoint\naction: run\n")

        result = scan_and_index_catalog(fs.base_path)

        assert result.ok
        assert len(result.items) == 2

        db_items = self.db.catalog.list()
        assert len(db_items) == 2
        assert {item.item_type for item in db_items} == {
            CatalogItemType.BLUEPRINT,
            CatalogItemType.STEP,
        }
        assert {item.key for item in db_items} == {"feature-dev", "git-check"}

        (fs.base_path / ".worktree/catalog/steps/git-check.yml").unlink()
        second_result = scan_and_index_catalog(fs.base_path)

        assert second_result.ok
        assert len(second_result.items) == 1
        second_db_items = self.db.catalog.list()
        assert len(second_db_items) == 1
        assert second_db_items[0].key == "feature-dev"

    def test_scan_and_index_catalog_sha_reflects_raw_content(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        workflow_file = fs.write_file(".worktree/catalog/blueprints/feature-dev.yml", "name: Feature Dev Blueprint\n")

        result1 = scan_and_index_catalog(fs.base_path)
        sha1 = result1.items[0].sha

        workflow_file.write_text("# comment\nname: Feature Dev Blueprint\n", encoding="utf-8")
        result2 = scan_and_index_catalog(fs.base_path)
        sha2 = result2.items[0].sha

        assert sha1 != sha2

    def test_scan_and_index_catalog_skips_unreadable_file(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/blueprints/feature-dev.yml", "name: Feature Dev Blueprint\n")

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            result = scan_and_index_catalog(fs.base_path)

        assert not result.ok
        assert result.items == []
        assert any("feature-dev.yml" in err and "permission denied" in err for err in result.errors)

    def test_catalog_db_list_by_name(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/blueprints/dup.yml", "name: dup\nsteps: []\n")
        fs.write_file(".worktree/catalog/steps/dup.yml", "name: dup\naction: run\n")
        result = scan_and_index_catalog(fs.base_path)

        all_duplicates = self.db.catalog.list_by_name("dup")
        assert len(all_duplicates) == 1
        assert all_duplicates[0].path.as_posix() == "blueprints/dup.yml"
        assert result.errors == [
            "Failed to index catalog record for 'steps/dup.yml': Invalid catalog item constraint violation"
        ]

        blueprint_duplicates = self.db.catalog.list_by_name("dup", item_type=CatalogItemType.BLUEPRINT)
        assert len(blueprint_duplicates) == 1
        assert blueprint_duplicates[0].path.as_posix() == "blueprints/dup.yml"

        nonexistent_duplicates = self.db.catalog.list_by_name("nonexistent")
        assert nonexistent_duplicates == []


class CatalogCrudOperationsTests:
    """Unit tests for item creation, retrieval, and deletion in the catalog."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_create_catalog_item_default(self, fs: FileSystem) -> None:
        record = create_catalog_item(
            item_type=CatalogItemType.BLUEPRINT,
            name="my-pipeline",
            path=fs.base_path,
        )

        assert record.item_type == CatalogItemType.BLUEPRINT
        assert record.name == "my-pipeline"
        assert record.key == "my-pipeline"
        assert record.sha.startswith("blueprint_")
        assert (fs.base_path / ".worktree" / "catalog" / "blueprints" / "my-pipeline.yml").exists()

        fetched = self.db.catalog.get_by_sha(record.sha)
        assert fetched is not None
        assert fetched.name == "my-pipeline"

    def test_create_catalog_item_from_template(self, fs: FileSystem) -> None:
        record = create_catalog_item(
            item_type=CatalogItemType.BLUEPRINT,
            name="from-template-blueprint",
            path=fs.base_path,
        )

        assert record.item_type == CatalogItemType.BLUEPRINT
        assert record.name == "from-template-blueprint"
        content = (fs.base_path / ".worktree" / "catalog" / "blueprints" / "from-template-blueprint.yml").read_text(
            encoding="utf-8"
        )
        assert "from-template-blueprint" in content

    @pytest.mark.parametrize(
        ("item_type", "dir_name", "expected_name_in_content"),
        [
            pytest.param(CatalogItemType.BLUEPRINT, "blueprints", "my-item", id="blueprint_item_type"),
            pytest.param(CatalogItemType.STEP, "steps", "my-step", id="step_item_type"),
        ],
    )
    def test_create_catalog_item_default_content_matches_current_template_contract(
        self,
        fs: FileSystem,
        item_type: CatalogItemType,
        dir_name: str,
        expected_name_in_content: str,
    ) -> None:
        record = create_catalog_item(item_type=item_type, name="my-item", path=fs.base_path)
        content = (fs.base_path / ".worktree" / "catalog" / dir_name / "my-item.yml").read_text(encoding="utf-8")

        assert content.strip()
        assert f"name: {expected_name_in_content}" in content
        assert record.name == "my-item"

    def test_create_catalog_item_collision_raises(self, fs: FileSystem) -> None:
        create_catalog_item(CatalogItemType.BLUEPRINT, "linter", path=fs.base_path)

        with pytest.raises(FileExistsError, match="collision"):
            create_catalog_item(CatalogItemType.BLUEPRINT, "linter", path=fs.base_path)

    def test_create_catalog_item_invalid_type_raises(self, fs: FileSystem) -> None:
        with pytest.raises(ValueError, match="Allowed choices"):
            create_catalog_item("invalid_type", "test", path=fs.base_path)

    def test_get_and_delete_catalog_item(self, fs: FileSystem) -> None:
        record = create_catalog_item(CatalogItemType.STEP, "checkpoint", path=fs.base_path)

        resolution_by_sha = get_catalog_item(record.sha, path=fs.base_path)
        assert resolution_by_sha.ok
        assert resolution_by_sha.resolved is not None
        assert resolution_by_sha.resolved.sha == record.sha

        resolution_by_name = get_catalog_item("checkpoint", path=fs.base_path)
        assert not resolution_by_name.ok
        assert resolution_by_name.status == DefinitionResolutionStatus.NOT_FOUND

        deleted = delete_catalog_item_by_sha_or_name(record.sha, path=fs.base_path)
        assert deleted is not None
        assert deleted.sha == record.sha
        assert not (fs.base_path / ".worktree" / "catalog" / record.path).exists()
        assert not get_catalog_item(record.sha, path=fs.base_path).ok

    def test_get_catalog_item_not_found(self, fs: FileSystem) -> None:
        resolution_result = get_catalog_item("missing-item", path=fs.base_path)

        assert not resolution_result.ok
        assert resolution_result.status == DefinitionResolutionStatus.NOT_FOUND
        assert resolution_result.resolved is None
        assert any("not found" in err for err in resolution_result.errors)

    def test_get_catalog_item_duplicate_names(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/blueprints/shared.yml", "name: shared\nsteps: []\n")
        fs.write_file(".worktree/catalog/steps/shared.yml", "name: shared\naction: run\n")
        result = scan_and_index_catalog(fs.base_path)

        resolution_result = get_catalog_item("shared", path=fs.base_path)

        assert resolution_result.ok
        assert resolution_result.resolved is not None
        assert resolution_result.resolved.path.as_posix() == "blueprints/shared.yml"
        assert len(resolution_result.matches) == 1
        assert resolution_result.warnings == []
        assert result.errors == [
            "Failed to index catalog record for 'steps/shared.yml': Invalid catalog item constraint violation"
        ]

    def test_get_catalog_item_with_definition_cls(self, fs: FileSystem) -> None:
        record = create_catalog_item(CatalogItemType.BLUEPRINT, "sample-blueprint", path=fs.base_path)

        resolution_result = get_catalog_item("sample-blueprint", definition_cls=SampleDefinition, path=fs.base_path)

        assert resolution_result.ok
        assert resolution_result.definition is not None
        assert resolution_result.definition.name == record.name
        assert resolution_result.definition.description == "Custom blueprint"

    def test_get_catalog_item_with_definition_cls_load_error(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/blueprints/bad.yml", "invalid: yaml: [")
        scan_and_index_catalog(fs.base_path)

        resolution_result = get_catalog_item("bad", definition_cls=SampleDefinition, path=fs.base_path)

        assert not resolution_result.ok
        assert resolution_result.status == DefinitionResolutionStatus.LOAD_ERROR
        assert resolution_result.definition is None
        assert resolution_result.errors
