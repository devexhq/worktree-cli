"""Contract tests for common filesystem models."""

from __future__ import annotations

from pathlib import Path

import pytest

from worktree.common.filesystem.models import FilesystemPaths, GlobalPaths


class GlobalPathsTests:
    """Contract tests for canonical global filesystem paths."""

    def test_from_root_resolves_root_and_derives_global_hierarchy(self, tmp_path: Path) -> None:
        source_root = tmp_path / "nested" / "global-root"

        paths = GlobalPaths.from_root(source_root)

        expected_root = source_root.resolve()
        assert paths.root == expected_root
        assert paths.global_dir == expected_root / "global"
        assert paths.global_catalog_dir == expected_root / "global" / "catalog"
        assert paths.user_dir == expected_root / "user"
        assert paths.user_catalog_dir == expected_root / "user" / "catalog"
        assert paths.data_dir == expected_root / "data"
        assert paths.storage_dir == expected_root / "storage"


class FilesystemPathsTests:
    """Contract tests for project-aware workspace runtime paths."""

    def test_from_root_with_project_id_routes_runtime_paths_to_global_project_storage(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A project ID routes runtime paths globally while keeping sandboxes local."""
        global_root = tmp_path / "global"
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))

        paths = FilesystemPaths.from_root(tmp_path / "repository", project_id="project-626")

        project_storage = global_root / "storage" / "projects" / "project-626"
        assert paths.sessions_dir == project_storage / "sessions"
        assert paths.artifacts_dir == project_storage / "artifacts"
        assert paths.logs_dir == project_storage / "logs"
        assert paths.tmp_dir == project_storage / "tmp"
        assert paths.sandboxes_dir == tmp_path / "repository" / ".worktree" / "sandboxes"
        assert paths.project_storage_dir() == project_storage

    def test_from_root_without_project_id_keeps_all_runtime_paths_repository_local(self, tmp_path: Path) -> None:
        """No project ID keeps every runtime path under the repository workspace."""
        paths = FilesystemPaths.from_root(tmp_path / "repository")

        worktree_dir = tmp_path / "repository" / ".worktree"
        assert paths.sessions_dir == worktree_dir / "sessions"
        assert paths.artifacts_dir == worktree_dir / "artifacts"
        assert paths.logs_dir == worktree_dir / "logs"
        assert paths.tmp_dir == worktree_dir / "tmp"
        assert paths.sandboxes_dir == worktree_dir / "sandboxes"
        assert paths.project_storage_dir() is None
