"""Tests for CliContext initialization and configuration validation."""

from __future__ import annotations

import pytest

from tests.helpers import GitFileSystem
from worktree.cli.context import CliContext
from worktree.core.config import ConfigLoadError


class CliContextBuildTests:
    """Test suite for CliContext.build error reporting."""

    def test_build_succeeds_when_config_is_valid(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        context = CliContext.build()
        assert context is not None
        assert context.cwd == git_fs.base_path.resolve()
        assert context.config is not None
        assert context.config.project.name == git_fs.base_path.name

    def test_build_with_explicit_path(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        git_fs.init_repo()
        context = CliContext.build(path=git_fs.base_path)
        assert context is not None
        assert context.cwd == git_fs.base_path.resolve()
        assert context.fs.root_dir == git_fs.base_path.resolve()
        assert context.config is not None

    def test_build_raises_when_config_not_found(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        with pytest.raises(ConfigLoadError) as exc_info:
            CliContext.build()

        assert "CONFIG_NOT_FOUND" in str(exc_info.value)
        assert "wt init" in str(exc_info.value)

    def test_build_raises_when_schema_invalid(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        # Overwrite with incomplete config
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        with pytest.raises(ConfigLoadError) as exc_info:
            CliContext.build()

        assert "CONFIG_SCHEMA_INVALID" in str(exc_info.value)

    def test_build_raises_when_json_malformed(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_dir = git_fs.base_path / ".worktree"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{ broken json", encoding="utf-8")

        with pytest.raises(ConfigLoadError) as exc_info:
            CliContext.build()

        assert "CONFIG_MALFORMED_JSON" in str(exc_info.value)
