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


def test_ensure_catalog_dirs_creates_structure(tmp_path: Path) -> None:
    catalog_dir = ensure_catalog_dirs(tmp_path)
    assert catalog_dir == tmp_path / ".worktree" / "catalog"
    assert (catalog_dir / "workflows").is_dir()
    assert (catalog_dir / "tasks").is_dir()
    assert (catalog_dir / "steps").is_dir()


def test_compute_catalog_sha() -> None:
    sha, checksum = compute_catalog_sha(CatalogItemType.WORKFLOW, "name: test\n")
    assert sha.startswith("workflow_")
    assert len(sha) == 16  # "workflow_" (9) + 7 hex chars = 16
    assert len(checksum) == 64
    assert sha == f"workflow_{checksum[:7]}"


def test_scan_and_index_catalog(tmp_path: Path) -> None:
    catalog_dir = ensure_catalog_dirs(tmp_path)

    # Create dummy files
    wf_file = catalog_dir / "workflows" / "feature-dev.yml"
    wf_file.write_text("name: Feature Dev Workflow\n", encoding="utf-8")

    task_file = catalog_dir / "tasks" / "run-lint.yml"
    task_file.write_text("name: Run Linter\n", encoding="utf-8")

    step_file = catalog_dir / "steps" / "git-check.yml"
    step_file.write_text("name: Git Checkpoint\n", encoding="utf-8")

    result = scan_and_index_catalog(tmp_path)
    assert result.ok
    assert len(result.items) == 3

    # Check indexed DB items
    db_items = CatalogDb(tmp_path).list()
    assert len(db_items) == 3
    shas = {item.sha for item in db_items}
    assert any(sha.startswith("workflow_") for sha in shas)
    assert any(sha.startswith("task_") for sha in shas)
    assert any(sha.startswith("step_") for sha in shas)

    # Remove one file and verify DB purge on re-scan
    step_file.unlink()
    res2 = scan_and_index_catalog(tmp_path)
    assert res2.ok
    assert len(res2.items) == 2
    db_items2 = CatalogDb(tmp_path).list()
    assert len(db_items2) == 2


def test_scan_and_index_catalog_sha_reflects_raw_content(tmp_path: Path) -> None:
    """SHA must change when raw file content changes, even if parsed structure is unchanged."""
    catalog_dir = ensure_catalog_dirs(tmp_path)
    wf_file = catalog_dir / "workflows" / "feature-dev.yml"

    wf_file.write_text("name: Feature Dev Workflow\n", encoding="utf-8")
    result1 = scan_and_index_catalog(tmp_path)
    sha1 = result1.items[0].sha

    # Same parsed value, different raw text (extra comment/whitespace)
    wf_file.write_text("# comment\nname: Feature Dev Workflow\n", encoding="utf-8")
    result2 = scan_and_index_catalog(tmp_path)
    sha2 = result2.items[0].sha

    assert sha1 != sha2


def test_scan_and_index_catalog_skips_unreadable_file(tmp_path: Path) -> None:
    catalog_dir = ensure_catalog_dirs(tmp_path)
    wf_file = catalog_dir / "workflows" / "feature-dev.yml"
    wf_file.write_text("name: Feature Dev Workflow\n", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        result = scan_and_index_catalog(tmp_path)

    assert not result.ok
    assert len(result.items) == 0
    assert any("feature-dev.yml" in err and "permission denied" in err for err in result.errors)


def test_create_catalog_item_default(tmp_path: Path) -> None:
    record = create_catalog_item(
        item_type="workflow",
        name="my-pipeline",
        cwd=tmp_path,
    )
    assert record.item_type == CatalogItemType.WORKFLOW
    assert record.name == "my-pipeline"
    assert record.sha.startswith("workflow_")
    assert (tmp_path / ".worktree" / "catalog" / "workflows" / "my-pipeline.yml").exists()

    # DB verify
    fetched = CatalogDb(tmp_path).get_by_sha(record.sha)
    assert fetched is not None
    assert fetched.name == "my-pipeline"


def test_create_catalog_item_from_template(tmp_path: Path) -> None:
    record = create_catalog_item(
        item_type="workflow",
        name="from-template-wf",
        template_name="feature-dev",
        cwd=tmp_path,
    )
    assert record.item_type == CatalogItemType.WORKFLOW
    assert record.name == "from-template-wf"
    content = (tmp_path / ".worktree" / "catalog" / "workflows" / "from-template-wf.yml").read_text(encoding="utf-8")
    assert "feature-dev" in content or "Workflow" in content


def test_create_catalog_item_collision_raises(tmp_path: Path) -> None:
    create_catalog_item("task", "linter", cwd=tmp_path)
    with pytest.raises(FileExistsError, match="collision"):
        create_catalog_item("task", "linter", cwd=tmp_path)


def test_create_catalog_item_invalid_type_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Allowed choices"):
        create_catalog_item("invalid_type", "test", cwd=tmp_path)


def test_get_and_delete_catalog_item(tmp_path: Path) -> None:
    record = create_catalog_item("step", "checkpoint", cwd=tmp_path)

    # Retrieve by SHA
    found_by_sha = get_catalog_item(record.sha, cwd=tmp_path)
    assert found_by_sha is not None
    assert found_by_sha.sha == record.sha

    # Retrieve by Name
    found_by_name = get_catalog_item("checkpoint", cwd=tmp_path)
    assert found_by_name is not None
    assert found_by_name.sha == record.sha

    # Delete
    deleted = delete_catalog_item_by_sha_or_name(record.sha, cwd=tmp_path)
    assert deleted is not None
    assert deleted.sha == record.sha
    assert not (tmp_path / ".worktree" / "catalog" / record.path).exists()
    assert get_catalog_item(record.sha, cwd=tmp_path) is None
