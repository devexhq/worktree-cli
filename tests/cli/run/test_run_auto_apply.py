"""Tests for `wt run --auto-apply`."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.core.catalog.services.inventory import scan_and_index_catalog

runner = CliRunner()


class RunAutoApplyTests:
    """Integration tests for auto-applying sandbox changes on blueprint run."""

    def test_run_auto_apply_completed_applies_changes(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify changes in sandbox are automatically applied when run completes with --auto-apply."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)

        git_fs.create_task_file(
            "auto-task",
            description="Auto apply task",
            use_sandbox=True,
            steps=[
                {"id": "step-1", "run": "echo 'generated content' > gen.txt"},
            ],
        )
        scan_and_index_catalog(path=git_fs.base_path)

        result = runner.invoke(app, ["run", "auto-task", "--auto-apply"], catch_exceptions=False)
        assert result.exit_code == 0
        assert (git_fs.base_path / "gen.txt").exists()
        assert "generated content" in (git_fs.base_path / "gen.txt").read_text(encoding="utf-8")

    def test_run_auto_apply_failed_does_not_apply(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify changes are not applied when run fails."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)

        git_fs.create_task_file(
            "failing-task",
            description="Failing task",
            use_sandbox=True,
            steps=[
                {"id": "step-1", "run": "echo 'should not apply' > bad.txt"},
                {"id": "step-2", "run": "exit 1"},
            ],
        )
        scan_and_index_catalog(path=git_fs.base_path)

        result = runner.invoke(app, ["run", "failing-task", "--auto-apply", "--non-interactive"])
        assert result.exit_code == 1
        assert not (git_fs.base_path / "bad.txt").exists()
