"""Tests for CliContext initialization and configuration validation."""

from __future__ import annotations

import pytest

from tests.helpers import GitFileSystem
from worktree.cli.context import CliContext


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

    def test_build_reports_uninitialized_when_config_not_found(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        context = CliContext.build()
        assert context is None

        out = capsys.readouterr().out
        assert "Worktree workspace is not initialized." in out
        assert "Hint: Run 'wt init' to initialize Worktree in this repository." in out
        assert "Invalid Worktree Configuration" not in out

    def test_build_reports_invalid_config_when_schema_invalid(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        # Overwrite with incomplete config
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text('{"version": 1}\n', encoding="utf-8")

        context = CliContext.build()
        assert context is None

        out = capsys.readouterr().out
        assert "Invalid Worktree Configuration" in out
        assert "CONFIG_SCHEMA_INVALID" in out
        assert "Worktree workspace is not initialized." not in out

    def test_build_reports_invalid_config_when_json_malformed(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        config_dir = git_fs.base_path / ".worktree"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{ broken json", encoding="utf-8")

        context = CliContext.build()
        assert context is None

        out = capsys.readouterr().out
        assert "Invalid Worktree Configuration" in out
        assert "CONFIG_MALFORMED_JSON" in out
        assert "Worktree workspace is not initialized." not in out
