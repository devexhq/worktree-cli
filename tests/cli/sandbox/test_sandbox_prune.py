"""Single-tier CLI integration tests for wt sandbox prune."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import assert_model_equal
from worktree.cli import app
from worktree.core.sandbox.models import SandboxPruneResult, SandboxPruneStatus


class SandboxPruneCliIntegrationTests:
    """Typer runner integration tests for wt sandbox prune."""

    @pytest.mark.parametrize(
        ("flag", "dry_run", "force"),
        [
            pytest.param("--dry-run", True, False, id="dry-run"),
            pytest.param("--force", False, True, id="force"),
        ],
    )
    def test_sandbox_prune_cli_flag_wired_reports_nothing_exits_zero(
        self,
        cli_runner: CliRunner,
        sandbox_workspace: Path,
        dispatch_spy: list[Any],
        flag: str,
        dry_run: bool,
        force: bool,
    ) -> None:
        """wt sandbox prune --dry-run/--force on a healthy workspace exits 0, reports no stale sandboxes, and dispatches the exact empty DTO."""
        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "prune", flag])

        assert result.exit_code == 0
        assert "No stale sandboxes found." in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxPruneResult(
                status=SandboxPruneStatus.OK, dry_run=dry_run, force=force, items=[], errors=[], warnings=[], fixes=[]
            ),
        )

    def test_sandbox_prune_cli_renders_json(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """wt sandbox prune --dry-run --format json emits a SandboxPruneResult envelope wrapping the empty view."""
        result = cli_runner.invoke(
            app, ["-p", str(sandbox_workspace), "sandbox", "prune", "--dry-run", "--format", "json"]
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "SandboxPruneResult",
            "payload": {
                "status": "ok",
                "dry_run": True,
                "force": False,
                "items": [],
                "pruned_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
