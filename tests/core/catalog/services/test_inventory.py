"""Contract tests for the disk-backed multi-tier catalog index services."""

from __future__ import annotations

from pathlib import Path

from worktree.core.catalog.models import CatalogIndexEntry, CatalogItemType, CatalogTier
from worktree.core.catalog.services.inventory import (
    compute_catalog_sha,
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
