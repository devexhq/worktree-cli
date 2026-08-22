"""Unit tests for catalog directory scanner, legacy migration engine, and inventory CRUD functions."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from tests.helpers import FileSystem
from worktree.common.fs import (
    compute_content_checksum,
    delete_file,
    read_yaml_file,
)
from worktree.common.models import DefinitionResolutionStatus
from worktree.core.catalog.services.inventory import (
    compute_catalog_sha,
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    ensure_catalog_dirs,
    get_catalog_item,
    scan_and_index_catalog,
)
from worktree.core.db import (
    CatalogItemType,
    CatalogRepository,
)


def test_ensure_catalog_dirs_creates_structure(fs: FileSystem) -> None:
    catalog_dir = ensure_catalog_dirs(fs.base_path)
    assert catalog_dir == fs.base_path / ".worktree" / "catalog"
    assert (catalog_dir / "workflows").is_dir()
    assert (catalog_dir / "tasks").is_dir()
    assert (catalog_dir / "steps").is_dir()


def test_compute_catalog_sha() -> None:
    sha, checksum = compute_catalog_sha(CatalogItemType.WORKFLOW, "name: test\n")
    assert sha.startswith("workflow_")
    assert len(sha) == 16  # "workflow_" (9) + 7 hex chars = 16
    assert len(checksum) == 64
    assert sha == f"workflow_{checksum[:7]}"
    # Confirm it delegates to compute_content_checksum
    assert checksum == compute_content_checksum("name: test\n")


def test_common_fs_checksum_and_delete(fs: FileSystem) -> None:
    content = "test text"
    checksum = compute_content_checksum(content)
    assert len(checksum) == 64

    test_path = fs.base_path / "sample.txt"
    fs.write_file("sample.txt", content)

    yaml_file = read_yaml_file(test_path)
    assert yaml_file.checksum == checksum
    assert yaml_file.file_size == len(content.encode("utf-8"))

    assert delete_file(test_path) is True
    assert not test_path.exists()
    assert delete_file(test_path) is False


def test_scan_and_index_catalog(fs: FileSystem) -> None:
    ensure_catalog_dirs(fs.base_path)

    # Create dummy files
    fs.write_file(".worktree/catalog/workflows/feature-dev.yml", "name: Feature Dev Workflow\n")
    fs.write_file(".worktree/catalog/tasks/run-lint.yml", "name: Run Linter\n")
    step_file = fs.write_file(".worktree/catalog/steps/git-check.yml", "name: Git Checkpoint\n")

    result = scan_and_index_catalog(fs.base_path)
    assert result.ok
    assert len(result.items) == 3

    # Check indexed DB items
    db_items = CatalogRepository(fs.base_path).list()
    assert len(db_items) == 3
    sha_hashes = {item.sha for item in db_items}
    assert any(sha.startswith("workflow_") for sha in sha_hashes)
    assert any(sha.startswith("task_") for sha in sha_hashes)
    assert any(sha.startswith("step_") for sha in sha_hashes)

    # Remove one file and verify DB purge on re-scan
    step_file.unlink()
    second_result = scan_and_index_catalog(fs.base_path)
    assert second_result.ok
    assert len(second_result.items) == 2
    second_db_items = CatalogRepository(fs.base_path).list()
    assert len(second_db_items) == 2


def test_scan_and_index_catalog_sha_reflects_raw_content(fs: FileSystem) -> None:
    """SHA must change when raw file content changes, even if parsed structure is unchanged."""
    ensure_catalog_dirs(fs.base_path)
    workflow_file = fs.write_file(".worktree/catalog/workflows/feature-dev.yml", "name: Feature Dev Workflow\n")
    result1 = scan_and_index_catalog(fs.base_path)
    sha1 = result1.items[0].sha

    # Same parsed value, different raw text (extra comment/whitespace)
    workflow_file.write_text("# comment\nname: Feature Dev Workflow\n", encoding="utf-8")
    result2 = scan_and_index_catalog(fs.base_path)
    sha2 = result2.items[0].sha

    assert sha1 != sha2


def test_scan_and_index_catalog_skips_unreadable_file(fs: FileSystem) -> None:
    ensure_catalog_dirs(fs.base_path)
    fs.write_file(".worktree/catalog/workflows/feature-dev.yml", "name: Feature Dev Workflow\n")

    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        result = scan_and_index_catalog(fs.base_path)

    assert not result.ok
    assert len(result.items) == 0
    assert any("feature-dev.yml" in err and "permission denied" in err for err in result.errors)


def test_create_catalog_item_default(fs: FileSystem) -> None:
    record = create_catalog_item(
        item_type="workflow",
        name="my-pipeline",
        cwd=fs.base_path,
    )
    assert record.item_type == CatalogItemType.WORKFLOW
    assert record.name == "my-pipeline"
    assert record.sha.startswith("workflow_")
    assert (fs.base_path / ".worktree" / "catalog" / "workflows" / "my-pipeline.yml").exists()

    # DB verify
    fetched = CatalogRepository(fs.base_path).get_by_sha(record.sha)
    assert fetched is not None
    assert fetched.name == "my-pipeline"


def test_create_catalog_item_from_template(fs: FileSystem) -> None:
    record = create_catalog_item(
        item_type="workflow",
        name="from-template-wf",
        cwd=fs.base_path,
    )
    assert record.item_type == CatalogItemType.WORKFLOW
    assert record.name == "from-template-wf"
    content = (fs.base_path / ".worktree" / "catalog" / "workflows" / "from-template-wf.yml").read_text(
        encoding="utf-8"
    )
    assert "from-template-wf" in content


@pytest.mark.parametrize("item_type", ["workflow", "task", "step"])
def test_create_catalog_item_default_content_is_non_empty_and_unnamed(fs: FileSystem, item_type: str) -> None:
    """Default content for each type is non-empty and no longer contains the packaged placeholder name."""
    record = create_catalog_item(item_type=item_type, name="my-blueprint", cwd=fs.base_path)
    content = (fs.base_path / ".worktree" / "catalog" / f"{item_type}s" / "my-blueprint.yml").read_text(
        encoding="utf-8"
    )
    assert content.strip()
    assert "my-workflow" not in content
    assert "my-task" not in content
    assert "my-step" not in content
    assert record.name == "my-blueprint"


def test_create_catalog_item_collision_raises(fs: FileSystem) -> None:
    create_catalog_item("task", "linter", cwd=fs.base_path)
    with pytest.raises(FileExistsError, match="collision"):
        create_catalog_item("task", "linter", cwd=fs.base_path)


def test_create_catalog_item_invalid_type_raises(fs: FileSystem) -> None:
    with pytest.raises(ValueError, match="Allowed choices"):
        create_catalog_item("invalid_type", "test", cwd=fs.base_path)


def test_catalog_db_list_by_name(fs: FileSystem) -> None:
    ensure_catalog_dirs(fs.base_path)
    fs.write_file(".worktree/catalog/workflows/dup.yml", "name: dup\n")
    fs.write_file(".worktree/catalog/tasks/dup.yml", "name: dup\n")
    scan_and_index_catalog(fs.base_path)

    db = CatalogRepository(fs.base_path)
    all_duplicates = db.list_by_name("dup")
    assert len(all_duplicates) == 2
    assert [d.path.as_posix() for d in all_duplicates] == ["tasks/dup.yml", "workflows/dup.yml"]

    workflow_duplicates = db.list_by_name("dup", item_type=CatalogItemType.WORKFLOW)
    assert len(workflow_duplicates) == 1
    assert workflow_duplicates[0].path.as_posix() == "workflows/dup.yml"

    nonexistent_duplicates = db.list_by_name("nonexistent")
    assert len(nonexistent_duplicates) == 0


def test_get_and_delete_catalog_item(fs: FileSystem) -> None:
    record = create_catalog_item("step", "checkpoint", cwd=fs.base_path)

    # Retrieve by SHA
    resolution_by_sha = get_catalog_item(record.sha, cwd=fs.base_path)
    assert resolution_by_sha.ok
    assert resolution_by_sha.resolved is not None
    assert resolution_by_sha.resolved.sha == record.sha

    # Retrieve by Name
    resolution_by_name = get_catalog_item("checkpoint", cwd=fs.base_path)
    assert resolution_by_name.ok
    assert resolution_by_name.resolved is not None
    assert resolution_by_name.resolved.sha == record.sha

    # Delete
    deleted = delete_catalog_item_by_sha_or_name(record.sha, cwd=fs.base_path)
    assert deleted is not None
    assert deleted.sha == record.sha
    assert not (fs.base_path / ".worktree" / "catalog" / record.path).exists()
    assert not get_catalog_item(record.sha, cwd=fs.base_path).ok


def test_get_catalog_item_not_found(fs: FileSystem) -> None:
    resolution_result = get_catalog_item("missing-item", cwd=fs.base_path)
    assert not resolution_result.ok
    assert resolution_result.status == DefinitionResolutionStatus.NOT_FOUND
    assert resolution_result.resolved is None
    assert any("not found" in err for err in resolution_result.errors)


def test_get_catalog_item_duplicate_names(fs: FileSystem) -> None:
    ensure_catalog_dirs(fs.base_path)
    fs.write_file(".worktree/catalog/workflows/shared.yml", "name: shared\n")
    fs.write_file(".worktree/catalog/tasks/shared.yml", "name: shared\n")
    scan_and_index_catalog(fs.base_path)

    resolution_result = get_catalog_item("shared", cwd=fs.base_path)
    assert resolution_result.ok
    assert resolution_result.resolved is not None
    assert resolution_result.resolved.path.as_posix() == "tasks/shared.yml"  # tasks comes before workflows
    assert len(resolution_result.matches) == 2
    assert len(resolution_result.warnings) == 1
    assert "Duplicate catalog name 'shared'" in resolution_result.warnings[0]


class SampleDefinition(BaseModel):
    name: str
    description: str = ""


def test_get_catalog_item_with_definition_cls(fs: FileSystem) -> None:
    record = create_catalog_item("task", "sample-task", cwd=fs.base_path)

    resolution_result = get_catalog_item("sample-task", definition_cls=SampleDefinition, cwd=fs.base_path)
    assert resolution_result.ok
    assert resolution_result.definition is not None
    assert resolution_result.definition.name == record.name
    assert resolution_result.definition.description == "Custom task blueprint"


def test_get_catalog_item_with_definition_cls_load_error(fs: FileSystem) -> None:
    ensure_catalog_dirs(fs.base_path)
    fs.write_file(".worktree/catalog/tasks/bad.yml", "invalid: yaml: [")
    scan_and_index_catalog(fs.base_path)

    resolution_result = get_catalog_item("bad", definition_cls=SampleDefinition, cwd=fs.base_path)
    assert not resolution_result.ok
    assert resolution_result.status == DefinitionResolutionStatus.LOAD_ERROR
    assert resolution_result.definition is None
    assert len(resolution_result.errors) > 0
