"""CLI integration tests for wt blueprint create."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app


class BlueprintCreateCliIntegrationTests:
    """Typer runner integration tests for wt blueprint create."""

    def test_blueprint_create_cli_creates_item_terminal(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt blueprint create --name <name>: scaffolds a repo-tier file and renders confirmation; exit 0."""
        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "blueprint", "create", "--name", "new-blueprint"]
        )

        assert result.exit_code == 0
        assert "Created catalog blueprint" in result.stdout
        target_file = isolated_workspace / ".worktree" / "catalog" / "blueprints" / "new-blueprint.yml"
        assert target_file.is_file()

    def test_blueprint_create_cli_renders_json(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt blueprint create --name <name> --format json: envelope's item is tagged tier='repo', type='blueprint'."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "blueprint", "create", "--name", "json-blueprint", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["event_type"] == "CatalogCreateResult"
        assert payload["payload"]["item"]["tier"] == "repo"
        assert payload["payload"]["item"]["item_type"] == "blueprint"

    def test_blueprint_create_cli_collision_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt blueprint create --name <existing name>: exits 1 on path collision."""
        cli_runner.invoke(app, ["-p", str(isolated_workspace), "blueprint", "create", "--name", "dup-blueprint"])

        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "blueprint", "create", "--name", "dup-blueprint"]
        )

        assert result.exit_code == 1
        assert "collision" in result.stdout

    def test_blueprint_create_cli_requires_name_option(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt blueprint create with no --name exits nonzero (missing required option)."""
        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "blueprint", "create"])

        assert result.exit_code != 0
