"""Unit tests for worktree.common.filesystem facade and models."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.common.filesystem import Filesystem, FilesystemPaths, YamlFile


class TestFilesystemPaths:
    """Unit tests for FilesystemPaths model."""

    def test_from_root_creates_all_paths(self, fs: FileSystem) -> None:
        root = fs.base_path.resolve()
        paths = FilesystemPaths.from_root(root)

        assert paths.root_dir == root
        assert paths.worktree_dir == root / ".worktree"
        assert paths.config_file == root / ".worktree" / "config.json"
        assert paths.db_file == root / ".worktree" / "data.db"
        assert paths.catalog_dir == root / ".worktree" / "catalog"
        assert paths.logs_dir == root / ".worktree" / "logs"
        assert paths.sessions_dir == root / ".worktree" / "sessions"
        assert paths.artifacts_dir == root / ".worktree" / "artifacts"
        assert paths.tmp_dir == root / ".worktree" / "tmp"
        assert paths.sandboxes_dir == root / ".worktree" / "sandboxes"
        assert paths.lock_file == root / ".worktree" / "worktree.lock"
        assert paths.gitignore_file == root / ".gitignore"
        assert paths.catalog_templates_dir is not None

    def test_session_dir_and_sandbox_dir(self, fs: FileSystem) -> None:
        root = fs.base_path.resolve()
        paths = FilesystemPaths.from_root(root)

        assert paths.session_dir("s123") == root / ".worktree" / "sessions" / "s123"
        assert paths.sandbox_dir("sbx456") == root / ".worktree" / "sandboxes" / "sbx456"

    def test_rel_to_root(self, fs: FileSystem) -> None:
        root = fs.base_path.resolve()
        paths = FilesystemPaths.from_root(root)

        child = root / "src" / "main.py"
        assert paths.rel_to_root(child) == Path("src/main.py")
        assert paths.rel_to_root("src/main.py") == Path("src/main.py")

        outside = Path("/some/outside/path")
        assert paths.rel_to_root(outside) == outside


class TestFilesystemFacade:
    """Unit tests for Filesystem facade class."""

    def test_root_dir_resolution_and_paths(self, fs: FileSystem) -> None:
        fs.create_config_file()
        sub = fs.base_path / "a" / "b"
        sub.mkdir(parents=True)

        filesystem = Filesystem(sub)
        assert filesystem.root_dir == fs.base_path.resolve()
        assert filesystem.worktree_dir == fs.base_path.resolve() / ".worktree"
        assert filesystem.config_file == fs.base_path.resolve() / ".worktree" / "config.json"
        assert filesystem.db_file == fs.base_path.resolve() / ".worktree" / "data.db"
        assert filesystem.catalog_dir == fs.base_path.resolve() / ".worktree" / "catalog"
        assert filesystem.logs_dir == fs.base_path.resolve() / ".worktree" / "logs"
        assert filesystem.sessions_dir == fs.base_path.resolve() / ".worktree" / "sessions"
        assert filesystem.artifacts_dir == fs.base_path.resolve() / ".worktree" / "artifacts"
        assert filesystem.tmp_dir == fs.base_path.resolve() / ".worktree" / "tmp"
        assert filesystem.sandboxes_dir == fs.base_path.resolve() / ".worktree" / "sandboxes"
        assert filesystem.lock_file == fs.base_path.resolve() / ".worktree" / "worktree.lock"
        assert filesystem.gitignore_file == fs.base_path.resolve() / ".gitignore"
        assert filesystem.catalog_templates_dir is not None

    def test_dynamic_getattr_delegates_to_paths(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)
        assert filesystem.session_dir("sess_1") == fs.base_path.resolve() / ".worktree" / "sessions" / "sess_1"
        assert filesystem.sandbox_dir("sbx_1") == fs.base_path.resolve() / ".worktree" / "sandboxes" / "sbx_1"
        assert filesystem.rel_to_root(fs.base_path / "foo.txt") == Path("foo.txt")

    def test_getattr_raises_attribute_error_for_unknown(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)
        with pytest.raises(AttributeError, match="'Filesystem' object has no attribute 'nonexistent_property'"):
            _ = filesystem.nonexistent_property

    def test_repr(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)
        assert repr(filesystem) == f"Filesystem(root={fs.base_path.resolve()!r})"

    def test_write_and_delete_operations(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)

        target_txt = fs.base_path / "hello.txt"
        filesystem.write_text(target_txt, "world")
        assert target_txt.read_text(encoding="utf-8") == "world"

        target_json = fs.base_path / "data.json"
        filesystem.write_json(target_json, {"k": "v"})
        assert target_json.read_text(encoding="utf-8") == '{\n  "k": "v"\n}\n'

        assert filesystem.delete_file(target_txt) is True
        assert not target_txt.exists()
        assert filesystem.delete_file(target_txt) is False

    def test_yaml_operations(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)

        yaml_path = fs.base_path / "test.yml"
        yaml_path.write_text("name: my-item\nvalue: 42\n", encoding="utf-8")

        yaml_file = filesystem.read_yaml(yaml_path)
        assert isinstance(yaml_file, YamlFile)
        assert yaml_file.name == "my-item"
        assert yaml_file.parsed == {"name": "my-item", "value": 42}

        entries = filesystem.scan_yaml(fs.base_path)
        assert len(entries) == 1
        assert entries[0].name == "my-item"

    def test_git_operations(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)

        assert filesystem.is_git_repo() is False

        (fs.base_path / ".git").mkdir()
        assert filesystem.is_git_repo() is True

        assert filesystem.update_gitignore() is True
        assert "/.worktree/" in (fs.base_path / ".gitignore").read_text(encoding="utf-8")

    def test_checksum(self, fs: FileSystem) -> None:
        filesystem = Filesystem(fs.base_path)
        cs1 = filesystem.checksum("hello")
        cs2 = Filesystem.compute_checksum("hello")
        assert cs1 == cs2
        assert len(cs1) == 64


class TestFilesystemSingleton:
    """Unit tests for Filesystem singleton lifecycle and configuration."""

    def test_singleton_identity(self, fs: FileSystem) -> None:
        Filesystem.configure(fs.base_path)
        fs1 = Filesystem()
        fs2 = Filesystem()
        assert fs1 is fs2
        assert fs1.root_dir == fs.base_path.resolve()

    def test_configure_changes_root(self, fs: FileSystem) -> None:
        p1 = fs.base_path / "ws1"
        p2 = fs.base_path / "ws2"
        p1.mkdir()
        p2.mkdir()

        fs1 = Filesystem.configure(p1)
        assert fs1.root_dir == p1.resolve()

        fs2 = Filesystem.configure(p2)
        assert fs2.root_dir == p2.resolve()
        assert Filesystem() is fs2

    def test_reset_clears_singleton(self, fs: FileSystem) -> None:
        Filesystem.configure(fs.base_path)
        fs1 = Filesystem()
        Filesystem.reset()
        fs2 = Filesystem()
        assert fs1 is not fs2

    def test_explicit_path_returns_distinct_instance(self, fs: FileSystem) -> None:
        p1 = fs.base_path / "ws1"
        p2 = fs.base_path / "ws2"
        p1.mkdir()
        p2.mkdir()

        Filesystem.configure(p1)
        singleton = Filesystem()
        explicit = Filesystem(p2)

        assert singleton is not explicit
        assert explicit.root_dir == p2.resolve()
        assert Filesystem() is singleton
