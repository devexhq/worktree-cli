"""Tests for `getworktree.core.catalog.services.seeder`."""

from __future__ import annotations

from getworktree.core.catalog.services.seeder import (
    seed_all_catalog_templates,
    seed_catalog_templates,
)
from getworktree.core.db import CatalogItemType
from tests.helpers import FileSystem


class SeedCatalogTemplatesTests:
    """Tests for `seed_catalog_templates`."""

    def test_creates_missing_files(self, fs: FileSystem) -> None:
        result = seed_catalog_templates(CatalogItemType.WORKFLOW, cwd=fs.base_path)

        assert result.ok
        assert {path.name for path in result.created_files} == {
            "fix-tests.yml",
            "review-fix.yml",
        }
        target_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        assert (target_dir / "fix-tests.yml").is_file()
        assert (target_dir / "review-fix.yml").is_file()

    def test_skips_existing_files_by_default(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "fix-tests.yml"
        target.write_text("custom\n", encoding="utf-8")

        result = seed_catalog_templates(CatalogItemType.WORKFLOW, cwd=fs.base_path)

        assert result.ok
        assert target in result.skipped_existing_files
        assert target.read_text(encoding="utf-8") == "custom\n"

    def test_force_overwrites_existing_files(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "review-fix.yml"
        target.write_text("custom\n", encoding="utf-8")

        result = seed_catalog_templates(CatalogItemType.WORKFLOW, cwd=fs.base_path, force=True)

        assert result.ok
        assert target in result.overwritten_files
        assert "version:" in target.read_text(encoding="utf-8")

    def test_handles_partial_existing_state(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = target_dir / "fix-tests.yml"
        existing.write_text("custom\n", encoding="utf-8")

        result = seed_catalog_templates(CatalogItemType.WORKFLOW, cwd=fs.base_path)

        assert result.ok
        assert existing in result.skipped_existing_files
        assert (target_dir / "review-fix.yml") in result.created_files

    def test_reports_directory_collisions(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        target_dir.mkdir(parents=True, exist_ok=True)
        collision = target_dir / "fix-tests.yml"
        collision.mkdir()

        result = seed_catalog_templates(CatalogItemType.WORKFLOW, cwd=fs.base_path)

        assert not result.ok
        assert any(str(collision) in error for error in result.errors)
        assert (target_dir / "review-fix.yml") in result.created_files

    def test_no_source_wt_dir_is_a_no_op(self, fs: FileSystem) -> None:
        """Tasks/steps currently have no curated `wt/` seed files."""
        result = seed_catalog_templates(CatalogItemType.TASK, cwd=fs.base_path)

        assert result.ok
        assert result.created_files == []
        assert result.skipped_existing_files == []
        assert result.overwritten_files == []
        assert result.errors == []


class SeedAllCatalogTemplatesTests:
    """Tests for `seed_all_catalog_templates`."""

    def test_aggregates_all_three_types(self, fs: FileSystem) -> None:
        result = seed_all_catalog_templates(cwd=fs.base_path)

        assert result.ok
        assert {path.name for path in result.created_files} == {
            "fix-tests.yml",
            "review-fix.yml",
        }
        workflows_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        assert (workflows_dir / "fix-tests.yml").is_file()
        assert (workflows_dir / "review-fix.yml").is_file()

    def test_force_overwrites_across_all_types(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / ".worktree" / "catalog" / "workflows" / "wt"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "fix-tests.yml").write_text("custom\n", encoding="utf-8")

        result = seed_all_catalog_templates(cwd=fs.base_path, force=True)

        assert result.ok
        assert any(path.name == "fix-tests.yml" for path in result.overwritten_files)
