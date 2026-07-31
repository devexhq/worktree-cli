"""Tests for common filesystem and path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from getworktree.common.fs import atomic_write_json, is_git_repository, update_gitignore
from getworktree.common.utils import display_path, resolve_path_from_config


class AtomicWriteJsonTests:
    """Tests for atomic_write_json."""

    def test_writes_json_with_trailing_newline(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.json"
        atomic_write_json(path, {"a": 1})
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == {"a": 1}
        assert not path.with_name("cfg.json.tmp").exists()


class GitignoreTests:
    """Tests for update_gitignore."""

    def test_creates_gitignore(self, tmp_path: Path) -> None:
        path = tmp_path / ".gitignore"
        assert update_gitignore(path) is True
        assert "/.worktree/" in path.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / ".gitignore"
        update_gitignore(path)
        assert update_gitignore(path) is False


class DisplayPathTests:
    """Tests for display_path."""

    def test_relative_when_possible(self, tmp_path: Path) -> None:
        child = tmp_path / "a" / "b"
        assert display_path(child, tmp_path) == "a/b"


class ResolvePathFromConfigTests:
    """Tests for resolve_path_from_config."""

    def test_default_when_missing_file(self, tmp_path: Path) -> None:
        path = resolve_path_from_config(
            tmp_path / "missing.json", "db_path", "fallback.db"
        )
        assert path == Path("fallback.db")

    def test_reads_paths_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps({"paths": {"db_path": ".worktree/token_audit.db"}}),
            encoding="utf-8",
        )
        path = resolve_path_from_config(cfg, "db_path", "fallback.db")
        assert path == Path(".worktree/token_audit.db")


class IsGitRepositoryTests:
    """Tests for is_git_repository."""

    def test_detects_git_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert is_git_repository(tmp_path) is True
        assert is_git_repository(tmp_path / "nope") is False
