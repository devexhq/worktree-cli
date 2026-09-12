"""Tests for Config facade singleton lifecycle and filesystem integration."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.common.filesystem import Filesystem as WtFilesystem
from worktree.core.config import Config


class ConfigSingletonTests:
    """Test suite verifying Config singleton access and lifecycle."""

    def test_singleton_identity(self, fs: FileSystem) -> None:
        WtFilesystem.configure(fs.base_path)
        cfg1 = Config()
        cfg2 = Config()
        assert cfg1 is cfg2
        assert cfg1.path == fs.base_path.resolve()

    def test_configure_updates_singleton(self, fs: FileSystem) -> None:
        other_path = fs.base_path / "other_workspace"
        other_path.mkdir()

        cfg1 = Config.configure(fs.base_path)
        assert cfg1.path == fs.base_path.resolve()

        cfg2 = Config.configure(other_path)
        assert cfg2.path == other_path.resolve()
        assert Config() is cfg2

    def test_reset_clears_singleton(self, fs: FileSystem) -> None:
        WtFilesystem.configure(fs.base_path)
        cfg1 = Config()
        Config.reset()
        cfg2 = Config()
        assert cfg1 is not cfg2

    def test_explicit_path_returns_distinct_instance(self, fs: FileSystem) -> None:
        other_path = fs.base_path / "explicit_dir"
        other_path.mkdir()

        WtFilesystem.configure(fs.base_path)
        singleton = Config()
        explicit = Config(other_path)

        assert singleton is not explicit
        assert explicit.path == other_path.resolve()
        assert Config() is singleton

    def test_config_mutation_invalidates_loaded_cache(self, fs: FileSystem) -> None:
        (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
        Config.configure(fs.base_path)
        cfg = Config()
        cfg.generate()

        assert cfg.agent.provider == "local"
        assert cfg.agent.model is None
        set_res = cfg.set("agent.model", "claude-3-5-sonnet")
        assert set_res.ok
        assert cfg.agent.model == "claude-3-5-sonnet"
