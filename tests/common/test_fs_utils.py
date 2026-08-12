"""Tests for common filesystem and path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from getworktree.common.fs import (
    atomic_write_json,
    atomic_write_text,
    get_session_dir,
    is_git_repository,
    update_gitignore,
)
from getworktree.common.utils import display_path, resolve_path_from_config
from tests.helpers import FileSystem


class SessionDirTests:
    """Tests for get_session_dir."""

    def test_returns_sessions_path(self, fs: FileSystem) -> None:
        path = get_session_dir(fs.base_path, "sbx_12345678")
        assert path == fs.base_path / ".worktree" / "sessions" / "sbx_12345678"


class AtomicWriteJsonTests:
    """Tests for atomic_write_json."""

    def test_writes_json_with_trailing_newline(self, fs: FileSystem) -> None:
        path = fs.base_path / "cfg.json"
        atomic_write_json(path, {"a": 1})
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == {"a": 1}
        assert not path.with_name("cfg.json.tmp").exists()


class AtomicWriteTextTests:
    """Tests for atomic_write_text."""

    def test_writes_text_utf8(self, fs: FileSystem) -> None:
        path = fs.base_path / "sub" / "diff.patch"
        atomic_write_text(path, "diff content\n")
        assert path.read_text(encoding="utf-8") == "diff content\n"
        assert not path.with_name("diff.patch.tmp").exists()


class GitignoreTests:
    """Tests for update_gitignore."""

    def test_creates_gitignore(self, fs: FileSystem) -> None:
        path = fs.base_path / ".gitignore"
        assert update_gitignore(path) is True
        assert "/.worktree/" in path.read_text(encoding="utf-8")

    def test_idempotent(self, fs: FileSystem) -> None:
        path = fs.base_path / ".gitignore"
        update_gitignore(path)
        assert update_gitignore(path) is False

    def test_appends_when_missing_entry(self, fs: FileSystem) -> None:
        path = fs.base_path / ".gitignore"
        path.write_text("node_modules/\n", encoding="utf-8")
        assert update_gitignore(path) is True
        text = path.read_text(encoding="utf-8")
        assert text.startswith("node_modules/\n")
        assert "/.worktree/" in text

    def test_noop_when_worktree_already_listed(self, fs: FileSystem) -> None:
        path = fs.base_path / ".gitignore"
        path.write_text(".worktree\n", encoding="utf-8")
        assert update_gitignore(path) is False
        assert path.read_text(encoding="utf-8") == ".worktree\n"


class DisplayPathTests:
    """Tests for display_path."""

    def test_relative_when_possible(self, fs: FileSystem) -> None:
        child = fs.base_path / "a" / "b"
        assert display_path(child, fs.base_path) == "a/b"


class ResolvePathFromConfigTests:
    """Tests for resolve_path_from_config."""

    def test_default_when_missing_file(self, fs: FileSystem) -> None:
        path = resolve_path_from_config(fs.base_path / "missing.json", "db_path", "fallback.db")
        assert path == Path("fallback.db")

    def test_reads_paths_key(self, fs: FileSystem) -> None:
        cfg = fs.base_path / "config.json"
        cfg.write_text(
            json.dumps({"paths": {"db_path": ".worktree/data.db"}}),
            encoding="utf-8",
        )
        path = resolve_path_from_config(cfg, "db_path", "fallback.db")
        assert path == Path(".worktree/data.db")


class IsGitRepositoryTests:
    """Tests for is_git_repository."""

    def test_detects_git_dir(self, fs: FileSystem) -> None:
        (fs.base_path / ".git").mkdir()
        assert is_git_repository(fs.base_path) is True
        assert is_git_repository(fs.base_path / "nope") is False

    def test_detects_git_file(self, fs: FileSystem) -> None:
        (fs.base_path / ".git").write_text("gitdir: ../.git/worktrees/feature\n", encoding="utf-8")
        assert is_git_repository(fs.base_path) is True
