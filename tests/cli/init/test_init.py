"""Single-tier CLI integration tests for wt init."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import assert_model_equal
from worktree.cli import app
from worktree.common.constants import REQUIRED_SUBDIRS
from worktree.core.bootstrap.models import BootstrapOutcome, BootstrapResult, WorkspaceInitResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult

_SEEDED_TEMPLATE_RELATIVE_PATHS = [
    "catalog/blueprints/wt/fix-tests.yml",
    "catalog/blueprints/wt/review-fix.yml",
    "catalog/steps/wt/ai-code-patcher.yml",
    "catalog/steps/wt/ai-planner.yml",
    "catalog/steps/wt/ai-reviewer.yml",
    "catalog/steps/wt/git-sync-base.yml",
    "catalog/steps/wt/run-tests.yml",
]


def _init_git_repo(path: Path) -> None:
    """Initialize a bare git repository at path with a committable identity."""
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True, text=True
    )


def _worktree_dir(workspace: Path) -> Path:
    return workspace / ".worktree"


def _seeded_template_paths(workspace: Path) -> list[Path]:
    return [_worktree_dir(workspace) / rel for rel in _SEEDED_TEMPLATE_RELATIVE_PATHS]


class InitCliIntegrationTests:
    """Typer runner integration tests for wt init."""

    def test_init_cli_fresh_git_repo_creates_workspace_exits_zero(
        self, cli_runner: CliRunner, tmp_path: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt init: fresh git repo, exit 0, config.json and data.db created, dispatched WorkspaceInitResult.bootstrap_result.outcome=INITIALIZED."""
        _init_git_repo(tmp_path)

        result = cli_runner.invoke(app, ["-p", str(tmp_path), "init"])

        assert result.exit_code == 0
        worktree_dir = _worktree_dir(tmp_path)
        assert (worktree_dir / "config.json").exists()
        assert (worktree_dir / "data.db").exists()
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            WorkspaceInitResult(
                bootstrap_result=BootstrapResult(
                    root_path=worktree_dir,
                    outcome=BootstrapOutcome.INITIALIZED,
                    root_created=True,
                    dirs_created=[worktree_dir / name for name in REQUIRED_SUBDIRS],
                    dirs_existing=[],
                    repaired=False,
                    seed_result=SeedResult(
                        created_files=[],
                        skipped_existing_files=[],
                        overwritten_files=[],
                        errors=[],
                        warnings=[],
                        fixes=[],
                    ),
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                config_result=ConfigGenerationResult(
                    created=True,
                    skipped_existing=False,
                    repaired=False,
                    overwritten=False,
                    inserted_keys=[],
                    config_path=worktree_dir / "config.json",
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                seed_result=SeedResult(
                    created_files=_seeded_template_paths(tmp_path),
                    skipped_existing_files=[],
                    overwritten_files=[],
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                failure_mode=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_init_cli_rerun_without_flags_skips_existing_exits_zero(
        self, cli_runner: CliRunner, tmp_path: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt init: second invocation with no flags exits 0, dispatched WorkspaceInitResult.bootstrap_result.outcome=ALREADY_INITIALIZED."""
        _init_git_repo(tmp_path)
        cli_runner.invoke(app, ["-p", str(tmp_path), "init"])
        dispatch_spy.clear()

        result = cli_runner.invoke(app, ["-p", str(tmp_path), "init"])

        assert result.exit_code == 0
        worktree_dir = _worktree_dir(tmp_path)
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            WorkspaceInitResult(
                bootstrap_result=BootstrapResult(
                    root_path=worktree_dir,
                    outcome=BootstrapOutcome.ALREADY_INITIALIZED,
                    root_created=False,
                    dirs_created=[],
                    dirs_existing=[worktree_dir / name for name in REQUIRED_SUBDIRS],
                    repaired=False,
                    seed_result=SeedResult(
                        created_files=[],
                        skipped_existing_files=[],
                        overwritten_files=[],
                        errors=[],
                        warnings=[],
                        fixes=[],
                    ),
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                config_result=ConfigGenerationResult(
                    created=False,
                    skipped_existing=True,
                    repaired=False,
                    overwritten=False,
                    inserted_keys=[],
                    config_path=worktree_dir / "config.json",
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                seed_result=SeedResult(
                    created_files=[],
                    skipped_existing_files=_seeded_template_paths(tmp_path),
                    overwritten_files=[],
                    errors=[],
                    warnings=[],
                    fixes=[],
                ),
                failure_mode=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_init_cli_overwrite_flag_regenerates_default_config_exits_zero(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """wt init --overwrite: reverts a mutated project.name back to the workspace directory name, exit 0."""
        _init_git_repo(tmp_path)
        cli_runner.invoke(app, ["-p", str(tmp_path), "init"])
        config_path = tmp_path / ".worktree" / "config.json"
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["project"]["name"] = "mutated-name"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        result = cli_runner.invoke(app, ["-p", str(tmp_path), "init", "--overwrite"])

        assert result.exit_code == 0
        persisted = json.loads(config_path.read_text(encoding="utf-8"))
        assert persisted["project"]["name"] == tmp_path.name

    def test_init_cli_outside_git_repo_exits_one(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """wt init: non-git directory, exit 1, 'not a valid Git repository' in stdout, no .worktree/ created."""
        result = cli_runner.invoke(app, ["-p", str(tmp_path), "init"])

        assert result.exit_code == 1
        assert "not a valid Git repository" in result.stdout
        assert not (tmp_path / ".worktree").exists()

    def test_init_cli_json_format_emits_literal_wire_payload(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """wt init --format json: fresh git repo, stdout equals the literal WorkspaceInitView envelope."""
        _init_git_repo(tmp_path)

        result = cli_runner.invoke(app, ["-p", str(tmp_path), "init", "--format", "json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "WorkspaceInitResult",
            "payload": {
                "ok": True,
                "root_path": str(tmp_path / ".worktree"),
                "root_path_relative": ".worktree",
                "bootstrap_outcome": "initialized",
                "dirs_created": [
                    ".worktree/.meta",
                    ".worktree/sessions",
                    ".worktree/artifacts",
                    ".worktree/tmp",
                    ".worktree/logs",
                ],
                "config_created": True,
                "config_overwritten": False,
                "config_repaired": False,
                "config_skipped_existing": False,
                "config_path_relative": ".worktree/config.json",
                "inserted_keys": [],
                "seeded_files": [
                    ".worktree/catalog/blueprints/wt/fix-tests.yml",
                    ".worktree/catalog/blueprints/wt/review-fix.yml",
                    ".worktree/catalog/steps/wt/ai-code-patcher.yml",
                    ".worktree/catalog/steps/wt/ai-planner.yml",
                    ".worktree/catalog/steps/wt/ai-reviewer.yml",
                    ".worktree/catalog/steps/wt/git-sync-base.yml",
                    ".worktree/catalog/steps/wt/run-tests.yml",
                ],
                "skipped_seed_files": [],
                "overwritten_seed_files": [],
                "failure_mode": None,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
