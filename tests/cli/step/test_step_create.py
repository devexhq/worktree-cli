"""CLI integration tests for wt step create."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app


class StepCreateCliIntegrationTests:
    """Typer runner integration tests for wt step create."""

    def test_step_create_cli_creates_item_terminal(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt step create --name <name>: scaffolds a repo-tier file and renders confirmation; exit 0."""
        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "step", "create", "--name", "new-step"])

        assert result.exit_code == 0
        assert "Created catalog blueprint" in result.stdout
        target_file = isolated_workspace / ".worktree" / "catalog" / "steps" / "new-step.yml"
        assert target_file.is_file()

    def test_step_create_cli_renders_json(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt step create --name <name> --format json: envelope's item is tagged tier='repo', type='step'."""
        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "step", "create", "--name", "json-step", "--format", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["event_type"] == "CatalogCreateResult"
        assert payload["payload"]["item"]["tier"] == "repo"
        assert payload["payload"]["item"]["item_type"] == "step"

    def test_step_create_cli_collision_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt step create --name <existing name>: exits 1 on path collision."""
        cli_runner.invoke(app, ["-p", str(isolated_workspace), "step", "create", "--name", "dup-step"])

        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "step", "create", "--name", "dup-step"])

        assert result.exit_code == 1
        assert "collision" in result.stdout

    def test_step_create_cli_requires_name_option(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt step create with no --name exits nonzero (missing required option)."""
        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "step", "create"])

        assert result.exit_code != 0
