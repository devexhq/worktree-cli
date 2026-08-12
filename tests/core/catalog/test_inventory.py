"""Unit tests for catalog directory scanner, legacy migration engine, and inventory CRUD functions."""

from pathlib import Path
from unittest.mock import patch

import pytest

from getworktree.core.catalog.inventory import (
    compute_catalog_sha,
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    ensure_catalog_dirs,
    get_catalog_item,
    scan_and_index_catalog,
)
from getworktree.core.db import (
    CatalogDb,
    CatalogItemType,
)
from tests.helpers import FileSystem


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
    db_items = CatalogDb(fs.base_path).list()
    assert len(db_items) == 3
    shas = {item.sha for item in db_items}
    assert any(sha.startswith("workflow_") for sha in shas)
    assert any(sha.startswith("task_") for sha in shas)
    assert any(sha.startswith("step_") for sha in shas)

    # Remove one file and verify DB purge on re-scan
    step_file.unlink()
    res2 = scan_and_index_catalog(fs.base_path)
    assert res2.ok
    assert len(res2.items) == 2
    db_items2 = CatalogDb(fs.base_path).list()
    assert len(db_items2) == 2


def test_scan_and_index_catalog_sha_reflects_raw_content(fs: FileSystem) -> None:
    """SHA must change when raw file content changes, even if parsed structure is unchanged."""
    ensure_catalog_dirs(fs.base_path)
    wf_file = fs.write_file(".worktree/catalog/workflows/feature-dev.yml", "name: Feature Dev Workflow\n")
    result1 = scan_and_index_catalog(fs.base_path)
    sha1 = result1.items[0].sha

    # Same parsed value, different raw text (extra comment/whitespace)
    wf_file.write_text("# comment\nname: Feature Dev Workflow\n", encoding="utf-8")
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
    fetched = CatalogDb(fs.base_path).get_by_sha(record.sha)
    assert fetched is not None
    assert fetched.name == "my-pipeline"


def test_create_catalog_item_from_template(fs: FileSystem) -> None:
    record = create_catalog_item(
        item_type="workflow",
        name="from-template-wf",
        template_name="feature-dev",
        cwd=fs.base_path,
    )
    assert record.item_type == CatalogItemType.WORKFLOW
    assert record.name == "from-template-wf"
    content = (fs.base_path / ".worktree" / "catalog" / "workflows" / "from-template-wf.yml").read_text(
        encoding="utf-8"
    )
    assert "feature-dev" in content or "Workflow" in content


def test_create_catalog_item_collision_raises(fs: FileSystem) -> None:
    create_catalog_item("task", "linter", cwd=fs.base_path)
    with pytest.raises(FileExistsError, match="collision"):
        create_catalog_item("task", "linter", cwd=fs.base_path)


def test_create_catalog_item_invalid_type_raises(fs: FileSystem) -> None:
    with pytest.raises(ValueError, match="Allowed choices"):
        create_catalog_item("invalid_type", "test", cwd=fs.base_path)


def test_get_and_delete_catalog_item(fs: FileSystem) -> None:
    record = create_catalog_item("step", "checkpoint", cwd=fs.base_path)

    # Retrieve by SHA
    found_by_sha = get_catalog_item(record.sha, cwd=fs.base_path)
    assert found_by_sha is not None
    assert found_by_sha.sha == record.sha

    # Retrieve by Name
    found_by_name = get_catalog_item("checkpoint", cwd=fs.base_path)
    assert found_by_name is not None
    assert found_by_name.sha == record.sha

    # Delete
    deleted = delete_catalog_item_by_sha_or_name(record.sha, cwd=fs.base_path)
    assert deleted is not None
    assert deleted.sha == record.sha
    assert not (fs.base_path / ".worktree" / "catalog" / record.path).exists()
    assert get_catalog_item(record.sha, cwd=fs.base_path) is None
