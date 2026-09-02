from __future__ import annotations

from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem
from worktree.cli.cli import app

runner = CliRunner()


class CliPathOptionTests:
    """Test suite verifying global --path / -p functionality across commands."""

    def test_init_with_explicit_path(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / "custom_repo"
        target_dir.mkdir(parents=True)
        (target_dir / ".git").mkdir()

        result = runner.invoke(app, ["--path", str(target_dir), "init"])
        assert result.exit_code == 0
        assert (target_dir / ".worktree" / "config.json").is_file()
        assert (target_dir / ".worktree" / "data.db").is_file()

    def test_init_with_short_p_flag(self, fs: FileSystem) -> None:
        target_dir = fs.base_path / "short_flag_repo"
        target_dir.mkdir(parents=True)
        (target_dir / ".git").mkdir()

        result = runner.invoke(app, ["-p", str(target_dir), "init"])
        assert result.exit_code == 0
        assert (target_dir / ".worktree" / "config.json").is_file()

    def test_status_with_explicit_path(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        other_dir = git_fs.base_path.parent / "other_empty_dir"
        other_dir.mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["--path", str(git_fs.base_path), "status"])
        assert result.exit_code == 0
        assert "Workspace Status" in result.stdout

    def test_config_show_with_explicit_path(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()

        result = runner.invoke(app, ["-p", str(git_fs.base_path), "config", "show"])
        assert result.exit_code == 0
        assert f"Config: {(git_fs.base_path / '.worktree' / 'config.json').as_posix()}" in result.stdout
