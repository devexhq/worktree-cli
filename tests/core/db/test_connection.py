"""Contract tests for centralized database path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from worktree.core.db.connection import resolve_db_path


class ConnectionTests:
    """Contract tests for resolve_db_path's centralized global data directory resolution."""

    def test_resolve_db_path_targets_global_data_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """[tier-1/unit] resolve_db_path: WORKTREE_HOME=<tmp> yields <tmp>/data/worktree.db."""
        monkeypatch.setenv("WORKTREE_HOME", str(tmp_path))

        result = resolve_db_path()

        assert result == tmp_path.resolve() / "data" / "worktree.db"

    def test_resolve_db_path_defaults_to_home_worktree_when_no_env_override(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """[tier-1/unit] resolve_db_path: no WORKTREE_HOME yields Path.home()/.worktree/data/worktree.db."""
        monkeypatch.delenv("WORKTREE_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = resolve_db_path()

        assert result == tmp_path / ".worktree" / "data" / "worktree.db"

    def test_resolve_db_path_creates_parent_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """[tier-1/unit] resolve_db_path: WORKTREE_HOME=<tmp>/fresh (non-existent) creates <tmp>/fresh/data/ before returning."""
        fresh_home = tmp_path / "fresh"
        monkeypatch.setenv("WORKTREE_HOME", str(fresh_home))

        result = resolve_db_path()

        assert result.parent.is_dir()
        assert result == fresh_home.resolve() / "data" / "worktree.db"
