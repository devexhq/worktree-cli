"""Tests for project-aware diff artifact retrieval."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worktree.core.diff.models import DiffStatus
from worktree.core.diff.services import DiffService
from worktree.core.diff.writer import get_session_dir, write_session_diff
from worktree.core.project.models import ProjectIdentity
from worktree.core.project.services.identity import save_project_identity


class DiffServiceTests:
    """Integration tests for reading routed session diff artifacts."""

    def test_collect_with_project_identity_reads_global_session_patch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A global patch is returned with its exact path and contents."""
        global_root = tmp_path / "global"
        repository = tmp_path / "repository"
        identity = ProjectIdentity(id="project-626", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        patch_text = "diff --git a/file.txt b/file.txt\n-old\n+new\n"
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))
        save_project_identity(repository / ".worktree" / "project.json", identity)
        patch_path = write_session_diff(get_session_dir(repository, "session-626"), patch_text)

        result = DiffService(repository, session_id="session-626").collect()

        assert result.status == DiffStatus.OK
        assert result.session_id == "session-626"
        assert result.diff_text == patch_text
        assert result.artifact_path == patch_path

    def test_collect_with_project_identity_and_no_global_session_returns_session_not_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An absent global session returns not found without creating a directory."""
        global_root = tmp_path / "global"
        repository = tmp_path / "repository"
        identity = ProjectIdentity(id="project-626", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))
        save_project_identity(repository / ".worktree" / "project.json", identity)

        result = DiffService(repository, session_id="session-626").collect()

        session_dir = global_root / "storage" / "projects" / "project-626" / "sessions" / "session-626"
        assert result.status == DiffStatus.SESSION_NOT_FOUND
        assert not session_dir.exists()
