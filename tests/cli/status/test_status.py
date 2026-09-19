"""Single-tier CLI integration tests for wt status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import AnyValue, assert_model_equal
from worktree.cli import app
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import WorktreeConfig
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    DatabaseStatusInfo,
    GitStatusInfo,
    SandboxStatusInfo,
    WorktreeStatusResult,
)

_ANY_RAW_CONFIG = AnyValue(dict, "ANY_RAW_CONFIG")
_ANY_CONFIG = AnyValue(WorktreeConfig, "ANY_CONFIG")

_BRANCH_WARNING = "Active branch is 'main'. Automated workflows on primary branches are discouraged."
_AGENT_MODEL_WARNING = "Agent model is not configured (agent.model is null)."


def _expected_status_result(
    status_workspace: Path, *, is_dirty: bool, uncommitted_files: int, warnings: list[str]
) -> WorktreeStatusResult:
    """Build the expected WorktreeStatusResult for a fresh status_workspace, type-matching the embedded config."""
    return WorktreeStatusResult(
        root_dir=status_workspace,
        is_initialized=True,
        git=GitStatusInfo(is_git_repo=True, branch="main", is_dirty=is_dirty, uncommitted_files=uncommitted_files),
        config=ConfigStatusInfo.model_construct(
            status=ConfigLoadStatus.OK,
            config_path=status_workspace / ".worktree" / "config.json",
            is_valid=True,
            raw=_ANY_RAW_CONFIG,
            config=_ANY_CONFIG,
            errors=[],
            fixes=[],
        ),
        catalog=CatalogStatusInfo(
            exists=False,
            catalog_dir=status_workspace / ".worktree" / "catalog",
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        ),
        database=DatabaseStatusInfo(
            exists=True, db_path=status_workspace / ".worktree" / "data.db", is_accessible=True, total_runs=0
        ),
        sandboxes=SandboxStatusInfo(active_sandboxes=0, total_sandboxes=0, max_active_sandboxes=3),
        errors=[],
        warnings=warnings,
        fixes=[],
    )


class StatusCliIntegrationTests:
    """Typer runner integration tests for wt status."""

    def test_status_cli_clean_worktree_exits_zero(
        self, cli_runner: CliRunner, status_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt status on a clean git worktree exits 0, renders the bare branch name, and dispatches the exact DTO."""
        result = cli_runner.invoke(app, ["-p", str(status_workspace), "status"])

        assert result.exit_code == 0
        assert "main" in result.stdout
        assert "(dirty)" not in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            _expected_status_result(
                status_workspace,
                is_dirty=False,
                uncommitted_files=0,
                warnings=[_BRANCH_WARNING, _AGENT_MODEL_WARNING],
            ),
        )

    def test_status_cli_dirty_worktree_shows_dirty_branch_exits_zero(
        self, cli_runner: CliRunner, status_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt status with one untracked file exits 0, renders 'main (dirty)', and dispatches the exact DTO."""
        (status_workspace / "untracked.txt").write_text("scratch\n", encoding="utf-8")

        result = cli_runner.invoke(app, ["-p", str(status_workspace), "status"])

        assert result.exit_code == 0
        assert "main (dirty)" in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            _expected_status_result(
                status_workspace,
                is_dirty=True,
                uncommitted_files=1,
                warnings=[
                    _BRANCH_WARNING,
                    "Working tree has 1 uncommitted change(s).",
                    _AGENT_MODEL_WARNING,
                ],
            ),
        )

    def test_status_cli_renders_json(self, cli_runner: CliRunner, status_workspace: Path) -> None:
        """wt status --format json on a clean git worktree emits the literal StatusView payload."""
        result = cli_runner.invoke(app, ["-p", str(status_workspace), "status", "--format", "json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "WorktreeStatusResult",
            "payload": {
                "health": "ok",
                "root_dir": str(status_workspace),
                "project_name": "workspace",
                "config_status": "ok",
                "config_path_relative": ".worktree/config.json",
                "git_branch": "main",
                "git_is_dirty": False,
                "uncommitted_files": 0,
                "agent_model": None,
                "active_sandboxes": 0,
                "max_active_sandboxes": 3,
                "valid_catalog_items": 0,
                "total_catalog_items": 0,
                "total_runs": 0,
                "errors": [],
                "warnings": [
                    "Active branch is 'main'. Automated workflows on primary branches are discouraged.",
                    "Agent model is not configured (agent.model is null).",
                ],
                "remediations": [],
            },
        }
