"""Tests for `wt sandbox prune`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tests.helpers import (
    GitFileSystem,
    get_subcommand,
    get_subgroup,
    list_subcommands,
    make_cli_context,
)
from worktree.cli import app
from worktree.cli.sandbox.commands.sandbox_prune import sandbox_prune_command
from worktree.common.lock import LockTimeoutError
from worktree.core.db import (
    SandboxesRepository,
    SandboxRecord,
    SandboxStatus,
    WorktreeDb,
)
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox import (
    SandboxDetectionResult,
    SandboxDetectionStatus,
    SandboxPruneResult,
    SandboxPruneStatus,
)

runner = CliRunner()
DB_REL = ".worktree/data.db"


def _create_stale_branch(path: Path, branch_name: str) -> None:
    """Create a temporary git branch matching sandbox naming conventions."""
    subprocess.run(
        ["git", "branch", branch_name],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


def _create_stale_db_record(
    db: SandboxesRepository,
    sandbox_id: str,
    missing_path: Path,
) -> SandboxRecord:
    """Insert an active sandbox record whose on-disk directory does not exist."""
    return db.create(
        id=sandbox_id,
        branch_name=f"worktree/sandbox-{sandbox_id}",
        base_commit="abc1234",
        sandbox_path=missing_path,
    )


def _create_clean_orphan_dir(sandboxes_dir: Path, name: str) -> Path:
    """Create an empty directory inside sandboxes storage not tracked in DB."""
    orphan_dir = sandboxes_dir / name
    orphan_dir.mkdir(parents=True, exist_ok=True)
    return orphan_dir


def _create_dirty_orphan_dir(path: Path, sandboxes_dir: Path, name: str) -> Path:
    """Create a valid git worktree with uncommitted changes not tracked in DB."""
    dirty_dir = sandboxes_dir / name
    GitRunner.worktree_add(
        path,
        target_path=dirty_dir,
        branch=f"worktree/sandbox-{name}",
        base_ref="main",
    )
    (dirty_dir / "dirty.txt").write_text("uncommitted changes", encoding="utf-8")
    return dirty_dir


class SandboxPruneCommandDirectTests:
    """Direct sandbox_prune_command unit tests verifying return models and output."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

    def test_clean_repository_returns_ok_with_empty_message(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_prune_command(context)

        assert outcome.ok is True
        assert outcome.status == SandboxPruneStatus.OK
        assert outcome.pruned_count == 0
        assert len(outcome.items) == 0
        assert "No stale sandboxes found." in capsys.readouterr().out

    def test_stale_resources_pruned_successfully(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        sandboxes_dir = git_fs.base_path / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        orphan_dir = _create_clean_orphan_dir(sandboxes_dir, "orphan_1")
        missing_path = sandboxes_dir / "sbx_missing"
        _create_stale_db_record(self.db.sandboxes, "sbx_missing", missing_path)
        branch_name = "worktree/sandbox-stale_br"
        _create_stale_branch(git_fs.base_path, branch_name)

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_prune_command(context)

        assert outcome.ok is True
        assert outcome.pruned_count == 3
        assert not orphan_dir.exists()
        record = self.db.sandboxes.get("sbx_missing")
        assert record is not None
        assert record.status == SandboxStatus.CLEANED
        branches = GitRunner.list_branches(git_fs.base_path, pattern="worktree/sandbox-*")
        assert branch_name not in branches
        output = capsys.readouterr().out
        assert "Pruned" in output
        assert "orphan_1" in output
        assert "sbx_missing" in output
        assert branch_name in output

    def test_dry_run_leaves_resources_intact(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        sandboxes_dir = git_fs.base_path / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        orphan_dir = _create_clean_orphan_dir(sandboxes_dir, "orphan_dry")
        missing_path = sandboxes_dir / "sbx_missing_dry"
        _create_stale_db_record(self.db.sandboxes, "sbx_missing_dry", missing_path)
        branch_name = "worktree/sandbox-dry_br"
        _create_stale_branch(git_fs.base_path, branch_name)

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_prune_command(context, dry_run=True)

        assert outcome.ok is True
        assert outcome.dry_run is True
        assert outcome.pruned_count == 3
        assert orphan_dir.exists()
        record = self.db.sandboxes.get("sbx_missing_dry")
        assert record is not None
        assert record.status == SandboxStatus.ACTIVE
        branches = GitRunner.list_branches(git_fs.base_path, pattern="worktree/sandbox-*")
        assert branch_name in branches
        assert "Would prune" in capsys.readouterr().out

    def test_dirty_orphan_skipped_without_force(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        sandboxes_dir = git_fs.base_path / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dirty_dir = _create_dirty_orphan_dir(git_fs.base_path, sandboxes_dir, "dirty_1")

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_prune_command(context, force=False)

        assert outcome.ok is True
        assert outcome.skipped_count == 1
        assert outcome.pruned_count == 0
        assert dirty_dir.exists()
        output = capsys.readouterr().out
        assert "Skipped" in output

    def test_dirty_orphan_pruned_with_force(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        sandboxes_dir = git_fs.base_path / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dirty_dir = _create_dirty_orphan_dir(git_fs.base_path, sandboxes_dir, "dirty_force")

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_prune_command(context, force=True)

        assert outcome.ok is True
        assert outcome.pruned_count == 1
        assert outcome.skipped_count == 0
        assert not dirty_dir.exists()
        assert "Pruned" in capsys.readouterr().out

    def test_detection_git_failure_returns_not_ok(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        failure_detection = SandboxDetectionResult(
            status=SandboxDetectionStatus.GIT_FAILED,
            errors=["fatal: git broken"],
        )
        with patch("worktree.core.sandbox.services.pruner.SandboxDetector.detect", return_value=failure_detection):
            context = make_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_prune_command(context)

        assert outcome.ok is False
        assert outcome.status == SandboxPruneStatus.GIT_FAILED
        assert "fatal: git broken" in outcome.errors

    def test_lock_timeout_returns_not_ok(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        with patch(
            "worktree.core.sandbox.services.pruner.WorkspaceLock.__enter__",
            side_effect=LockTimeoutError("lock timeout"),
        ):
            context = make_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_prune_command(context)

        assert outcome.ok is False
        assert outcome.status == SandboxPruneStatus.LOCKED
        assert any("Failed to acquire workspace lock" in error for error in outcome.errors)


class SandboxPruneCliIntegrationTests:
    """CliRunner integration tests covering Typer CLI options, exit codes, and JSON formatting."""

    def test_help_lists_prune_subcommand(self) -> None:
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

        sandbox_group = get_subgroup(app, "sandbox")
        assert "prune" in list_subcommands(sandbox_group)

    def test_prune_help_documents_options(self) -> None:
        result = runner.invoke(app, ["sandbox", "prune", "--help"])
        assert result.exit_code == 0

        prune_command = get_subcommand(app, "sandbox", "prune")
        options: set[str] = set()
        for param in prune_command.params:
            options.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            options.update(secondary)
        assert {"--dry-run", "--force", "--format"} <= options

    def test_prune_cli_clean_repository_exits_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        result = runner.invoke(app, ["sandbox", "prune"])
        assert result.exit_code == 0
        assert "No stale sandboxes found." in result.stdout

    def test_prune_cli_dry_run_leaves_resources_intact(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        branch_name = "worktree/sandbox-dry_cli"
        _create_stale_branch(git_fs.base_path, branch_name)

        result = runner.invoke(app, ["sandbox", "prune", "--dry-run"])
        assert result.exit_code == 0
        assert "Would prune" in result.stdout
        branches = GitRunner.list_branches(git_fs.base_path, pattern="worktree/sandbox-*")
        assert branch_name in branches

    def test_prune_cli_force_deletes_dirty_orphan(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        sandboxes_dir = git_fs.base_path / ".worktree" / "sandboxes"
        sandboxes_dir.mkdir(parents=True, exist_ok=True)

        dirty_dir = _create_dirty_orphan_dir(git_fs.base_path, sandboxes_dir, "dirty_cli")

        result = runner.invoke(app, ["sandbox", "prune", "--force"])
        assert result.exit_code == 0
        assert not dirty_dir.exists()
        assert "Pruned" in result.stdout

    def test_prune_cli_json_format_emits_ndjson_event(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        result = runner.invoke(app, ["sandbox", "prune", "--format", "json"])
        assert result.exit_code == 0
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_type"] == "SandboxPruneResult"
        assert parsed["payload"]["status"] == "ok"
        assert parsed["payload"]["dry_run"] is False
        assert parsed["payload"]["force"] is False
        assert parsed["payload"]["items"] == []

    def test_prune_cli_failure_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        error_result = SandboxPruneResult(
            status=SandboxPruneStatus.ERROR,
            errors=["Prune execution failed"],
        )
        with patch("worktree.core.sandbox.services.pruner.SandboxPruner.prune", return_value=error_result):
            result = runner.invoke(app, ["sandbox", "prune"])

        assert result.exit_code == 1
        assert "Prune execution failed" in result.stdout

    def test_prune_cli_uninitialized_exits_nonzero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        result = runner.invoke(app, ["sandbox", "prune"])
        assert result.exit_code == 1
        assert "CONFIG_NOT_FOUND" in result.stdout or "Config Error" in result.stdout
