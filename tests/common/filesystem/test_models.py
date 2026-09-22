"""Contract tests for common filesystem models."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem.models import GlobalPaths


class GlobalPathsTests:
    """Contract tests for canonical global filesystem paths."""

    def test_from_root_resolves_root_and_derives_global_hierarchy(self, tmp_path: Path) -> None:
        source_root = tmp_path / "nested" / "global-root"

        paths = GlobalPaths.from_root(source_root)

        expected_root = source_root.resolve()
        assert paths.root == expected_root
        assert paths.global_dir == expected_root / "global"
        assert paths.user_dir == expected_root / "user"
        assert paths.user_catalog_dir == expected_root / "user" / "catalog"
        assert paths.data_dir == expected_root / "data"
        assert paths.storage_dir == expected_root / "storage"
