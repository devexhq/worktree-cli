"""Tests for project-aware runtime storage resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worktree.core.project.models import ProjectIdentity
from worktree.core.project.services.identity import save_project_identity
from worktree.core.project.services.storage import resolve_project_filesystem_paths


class ProjectStorageServiceTests:
    """Integration tests for resolving project-aware workspace paths."""

    def test_resolve_project_filesystem_paths_with_persisted_identity_returns_global_runtime_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A persisted identity selects global runtime storage and local sandboxes."""
        global_root = tmp_path / "global"
        repository = tmp_path / "repository"
        identity = ProjectIdentity(id="project-626", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))
        save_project_identity(repository / ".worktree" / "project.json", identity)

        paths = resolve_project_filesystem_paths(repository)

        project_storage = global_root / "storage" / "projects" / "project-626"
        assert paths.sessions_dir == project_storage / "sessions"
        assert paths.artifacts_dir == project_storage / "artifacts"
        assert paths.logs_dir == project_storage / "logs"
        assert paths.tmp_dir == project_storage / "tmp"
        assert paths.sandboxes_dir == repository / ".worktree" / "sandboxes"

    def test_resolve_project_filesystem_paths_without_identity_returns_legacy_runtime_paths(
        self, tmp_path: Path
    ) -> None:
        """No identity retains repository-local runtime storage."""
        repository = tmp_path / "repository"

        paths = resolve_project_filesystem_paths(repository)

        worktree_dir = repository / ".worktree"
        assert paths.sessions_dir == worktree_dir / "sessions"
        assert paths.artifacts_dir == worktree_dir / "artifacts"
        assert paths.logs_dir == worktree_dir / "logs"
        assert paths.tmp_dir == worktree_dir / "tmp"
        assert paths.sandboxes_dir == worktree_dir / "sandboxes"
        assert paths.project_storage_dir() is None

    def test_resolve_project_filesystem_paths_with_undecodable_identity_returns_legacy_runtime_paths(
        self, tmp_path: Path
    ) -> None:
        """Invalid UTF-8 identity bytes select the local fallback instead of raising."""
        repository = tmp_path / "repository"
        identity_path = repository / ".worktree" / "project.json"
        identity_path.parent.mkdir(parents=True)
        identity_path.write_bytes(b"\xff\xfe\x00invalid")

        paths = resolve_project_filesystem_paths(repository)

        worktree_dir = repository / ".worktree"
        assert paths.sessions_dir == worktree_dir / "sessions"
        assert paths.artifacts_dir == worktree_dir / "artifacts"
        assert paths.logs_dir == worktree_dir / "logs"
        assert paths.tmp_dir == worktree_dir / "tmp"
        assert paths.project_storage_dir() is None
