"""Contract tests for the disk-backed multi-tier catalog index services."""

from __future__ import annotations

from pathlib import Path

import pytest

from worktree.common.filesystem.services.global_root import resolve_global_paths
from worktree.core.catalog.models import CatalogIndexEntry, CatalogItemType, CatalogTier
from worktree.core.catalog.services.inventory import (
    compute_catalog_sha,
    create_catalog_item,
    load_catalog_index,
    resolve_catalog_records,
    scan_and_index_tier,
    tier_root,
)


def _write_blueprint(tier_dir: Path, stem: str, content: str) -> None:
    """Write one blueprint YAML file under a tier's blueprints/ subdirectory."""
    blueprints_dir = tier_dir / "blueprints"
    blueprints_dir.mkdir(parents=True, exist_ok=True)
    (blueprints_dir / f"{stem}.yml").write_text(content, encoding="utf-8")


class ScanAndIndexTierTests:
    """[tier-1/unit] Layer discovery contracts for scan_and_index_tier."""

    def test_scan_and_index_tier_repo_rewrites_index_json_from_disk_walk(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        content = 'version: "1.0"\nname: sample\ndescription: Sample blueprint\nsteps: []\n'
        tier_dir = tier_root(CatalogTier.REPO, repo_root=repo_root, global_root=None)
        _write_blueprint(tier_dir, "sample", content)

        result = scan_and_index_tier(CatalogTier.REPO, repo_root=repo_root, global_root=None)

        expected_sha, expected_checksum = compute_catalog_sha(CatalogItemType.BLUEPRINT, content)
        index = load_catalog_index(tier_dir)
        assert index.items == [
            CatalogIndexEntry(
                sha=expected_sha,
                key="sample",
                item_type=CatalogItemType.BLUEPRINT,
                name="sample",
                namespace=None,
                path=Path("blueprints/sample.yml"),
                checksum=expected_checksum,
            )
        ]
        assert result.errors == []

    def test_scan_and_index_tier_removes_stale_entry_when_file_deleted_since_last_sync(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        tier_dir = tier_root(CatalogTier.REPO, repo_root=repo_root, global_root=None)
        _write_blueprint(tier_dir, "sample", 'version: "1.0"\nname: sample\ndescription: Sample\nsteps: []\n')
        scan_and_index_tier(CatalogTier.REPO, repo_root=repo_root, global_root=None)

        (tier_dir / "blueprints" / "sample.yml").unlink()
        scan_and_index_tier(CatalogTier.REPO, repo_root=repo_root, global_root=None)

        index = load_catalog_index(tier_dir)
        assert index.items == []


class ResolveCatalogRecordsTests:
    """[tier-1/unit] Multi-tier precedence contracts for resolve_catalog_records."""

    def test_resolve_catalog_records_orders_repo_before_user_before_global(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"
        content = 'version: "1.0"\nname: shared\ndescription: Shared\nsteps: []\n'

        for tier in (CatalogTier.REPO, CatalogTier.USER, CatalogTier.GLOBAL):
            tier_dir = tier_root(tier, repo_root=repo_root, global_root=global_root)
            _write_blueprint(tier_dir, "shared", content)
            scan_and_index_tier(tier, repo_root=repo_root, global_root=global_root)

        records = resolve_catalog_records(repo_root=repo_root, global_root=global_root)
        shared_tiers = [record.tier for record in records if record.key == "shared"]

        assert shared_tiers == [CatalogTier.REPO, CatalogTier.USER, CatalogTier.GLOBAL]


class CreateCatalogItemTests:
    """[tier-1/unit] Multi-tier write, reindex, and lock-root contracts for create_catalog_item."""

    @pytest.mark.parametrize(
        ("tier", "expected_tier_dir_attr"),
        [
            pytest.param(CatalogTier.REPO, None, id="repo"),
            pytest.param(CatalogTier.USER, "user_catalog_dir", id="user"),
            pytest.param(CatalogTier.GLOBAL, "global_catalog_dir", id="global"),
        ],
    )
    def test_create_catalog_item_writes_yaml_under_selected_tier(
        self, tmp_path: Path, tier: CatalogTier, expected_tier_dir_attr: str | None
    ) -> None:
        """create_catalog_item: writes blueprints/<name>.yml under the selected tier's root and returns a CatalogRecord tagged with that tier."""
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"

        record = create_catalog_item(
            CatalogItemType.BLUEPRINT, "my-blueprint", tier=tier, repo_root=repo_root, global_root=global_root
        )

        expected_tier_dir = (
            getattr(resolve_global_paths(global_root), expected_tier_dir_attr)
            if expected_tier_dir_attr is not None
            else tier_root(CatalogTier.REPO, repo_root=repo_root, global_root=None)
        )
        assert record.tier == tier
        assert (expected_tier_dir / "blueprints" / "my-blueprint.yml").is_file()

    def test_create_catalog_item_user_tier_leaves_repo_and_global_index_untouched(self, tmp_path: Path) -> None:
        """create_catalog_item(tier=USER): only <global_root>/user/index.json is written; repo and global index.json files do not exist afterward."""
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"

        create_catalog_item(
            CatalogItemType.BLUEPRINT,
            "my-blueprint",
            tier=CatalogTier.USER,
            repo_root=repo_root,
            global_root=global_root,
        )

        global_paths = resolve_global_paths(global_root)
        assert not (tier_root(CatalogTier.REPO, repo_root=repo_root, global_root=None) / "index.json").exists()
        assert not (global_paths.global_catalog_dir / "index.json").exists()
        assert (global_paths.user_catalog_dir / "index.json").exists()

    def test_create_catalog_item_user_tier_acquires_lock_under_global_root_not_repo_root(self, tmp_path: Path) -> None:
        """create_catalog_item(tier=USER): <global_root>/.worktree/.lock exists afterward; <repo_root>/.worktree/.lock does not."""
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"

        create_catalog_item(
            CatalogItemType.BLUEPRINT,
            "my-blueprint",
            tier=CatalogTier.USER,
            repo_root=repo_root,
            global_root=global_root,
        )

        assert (global_root / ".worktree" / ".lock").exists()
        assert not (repo_root / ".worktree" / ".lock").exists()

    def test_create_catalog_item_collision_at_selected_tier_raises_file_exists_error(self, tmp_path: Path) -> None:
        """create_catalog_item(tier=USER): a pre-existing file at the USER tier's target path raises FileExistsError naming the USER-relative path, independent of any REPO-tier file at the same relative path."""
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"
        create_catalog_item(
            CatalogItemType.BLUEPRINT, "dup", tier=CatalogTier.USER, repo_root=repo_root, global_root=global_root
        )

        with pytest.raises(FileExistsError, match=r"blueprints/dup\.yml"):
            create_catalog_item(
                CatalogItemType.BLUEPRINT, "dup", tier=CatalogTier.USER, repo_root=repo_root, global_root=global_root
            )

    def test_create_catalog_item_auto_provisions_missing_user_tier_directories(self, tmp_path: Path) -> None:
        """create_catalog_item(tier=USER): a global_root with no existing user/catalog/{blueprints,steps} directories succeeds, creating both before the write."""
        repo_root = tmp_path / "repo"
        global_root = tmp_path / "global_home"

        create_catalog_item(
            CatalogItemType.BLUEPRINT, "first", tier=CatalogTier.USER, repo_root=repo_root, global_root=global_root
        )

        user_catalog_dir = resolve_global_paths(global_root).user_catalog_dir
        assert (user_catalog_dir / "blueprints").is_dir()
        assert (user_catalog_dir / "steps").is_dir()
