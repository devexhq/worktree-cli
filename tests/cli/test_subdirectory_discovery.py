"""Integration tests verifying CLI commands run correctly from subdirectories."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem
from worktree.cli.cli import app
from worktree.cli.context import CliContext
from worktree.core.config import ConfigLoadError

runner = CliRunner()


class SubdirectoryDiscoveryTests:
    """Verify repository and workspace root discovery when invoked from subdirectories."""

    def test_clicontext_build_from_subdirectory(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()
        sub = git_fs.base_path / "packages" / "app" / "src"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        context = CliContext.build()
        assert context is not None
        assert context.cwd == git_fs.base_path.resolve()
        assert (context.cwd / ".worktree" / "config.json").is_file()

    def test_cli_status_from_subdirectory(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()
        sub = git_fs.base_path / "src" / "deep" / "folder"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert git_fs.base_path.name in result.stdout
        assert "Workspace Status" in result.stdout
        assert "Uninitialized" not in result.stdout

    def test_cli_init_from_subdirectory(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sub = git_fs.base_path / "nested" / "subpackage"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (git_fs.base_path / ".worktree" / "config.json").is_file()
        assert (git_fs.base_path / ".worktree" / "data.db").is_file()
        assert not (sub / ".worktree").exists()
        assert "/.worktree/" in (git_fs.base_path / ".gitignore").read_text(encoding="utf-8")

    def test_cli_catalog_list_from_subdirectory(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()
        git_fs.create_workflow_file(name="sample-flow")
        sub = git_fs.base_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["catalog", "list"])
        assert result.exit_code == 0
        assert "sample-flow" in result.stdout

    def test_cli_config_show_from_subdirectory(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        git_fs.init_repo()
        sub = git_fs.base_path / "packages" / "frontend"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert git_fs.base_path.name in result.stdout

    def test_cli_status_non_git_uninitialized_from_subdirectory(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sub = fs.base_path / "sub" / "dir"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Uninitialized" in result.stdout or "not initialized" in result.stdout.lower()

    def test_cli_context_build_non_git_uninitialized_raises_config_load_error(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sub = fs.base_path / "sub" / "dir"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)

        with pytest.raises(ConfigLoadError):
            CliContext.build()
