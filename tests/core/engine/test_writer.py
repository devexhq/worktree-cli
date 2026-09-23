"""Tests for project-aware session run payload loading."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worktree.core.diff.writer import get_session_dir
from worktree.core.engine.models import SessionRunPayload
from worktree.core.engine.writer import load_session_run, write_session_run_json
from worktree.core.project.models import ProjectIdentity
from worktree.core.project.services.identity import save_project_identity


class SessionRunWriterTests:
    """Integration tests for reading project-aware run metadata."""

    def test_load_session_run_with_project_identity_reads_global_run_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A global run payload is read while a conflicting local payload is ignored."""
        global_root = tmp_path / "global"
        repository = tmp_path / "repository"
        identity = ProjectIdentity(id="project-626", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        global_payload = SessionRunPayload(
            session_id="session-626",
            name="Global session",
            status="completed",
            started_at="2026-01-01T00:00:00+00:00",
        )
        local_payload = SessionRunPayload(
            session_id="session-626",
            name="Local session",
            status="failed",
            started_at="2026-01-01T00:00:00+00:00",
        )
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))
        save_project_identity(repository / ".worktree" / "project.json", identity)
        write_session_run_json(get_session_dir(repository, "session-626"), global_payload)
        local_session_dir = repository / ".worktree" / "sessions" / "session-626"
        local_session_dir.mkdir(parents=True)
        write_session_run_json(local_session_dir, local_payload)

        payload = load_session_run(repository, "session-626")

        assert payload == global_payload
