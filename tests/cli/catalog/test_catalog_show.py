"""Dual-tier matrix tests for wt catalog show."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_show import catalog_show_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.db.facade import WorktreeDb


@pytest.fixture(autouse=True)
def _setup_workspace_config(isolated_workspace: Path) -> None:
    """Ensure workspace contains valid config.json for CLI context resolution."""
    config_path = isolated_workspace / ".worktree" / "config.json"
    payload = build_default_config("demo-workspace")
    Filesystem.atomic_write_json(config_path, payload)


def _make_context(workspace: Path) -> CliContext:
    """Create a configured CliContext bound to the test workspace."""
    fs = Filesystem.configure(workspace)
    return CliContext(cwd=workspace, db=WorktreeDb(path=workspace), fs=fs)


class CatalogShowRootTests:
    """Direct handler unit tests for catalog_show_command."""

    @pytest.mark.parametrize(
        ("item_type_str", "name", "rel_path"),
        [
            pytest.param("blueprint", "show-blueprint", Path("blueprints/show-blueprint.yml"), id="blueprint"),
            pytest.param("step", "show-step", Path("steps/show-step.yml"), id="step"),
        ],
    )
    def test_catalog_show_returns_disk_item(
        self,
        isolated_workspace: Path,
        item_type_str: str,
        name: str,
        rel_path: Path,
    ) -> None:
        """catalog_show_command returns on-disk blueprint details and content."""
        context = _make_context(isolated_workspace)
        create_result = catalog_create_command(context, item_type_str, name=name)
        if create_result.item is None:
            pytest.fail("Failed to scaffold blueprint")

        expected_file = isolated_workspace / ".worktree" / "catalog" / rel_path
        expected_content = expected_file.read_text(encoding="utf-8")

        result = catalog_show_command(context, name)

        assert result.item is not None
        assert result.item.id == create_result.item.id
        assert result.item.key == create_result.item.key
        assert result.item.sha == create_result.item.sha
        assert result.content == expected_content
        assert result.template_matches == []
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("fix-tests", id="bare-name"),
            pytest.param("wt/fix-tests", id="namespaced-name"),
        ],
    )
    def test_catalog_show_falls_back_to_bundled_template(self, isolated_workspace: Path, template_name: str) -> None:
        """catalog_show_command falls back to packaged template when absent from disk."""
        context = _make_context(isolated_workspace)
        expected_file = Filesystem().catalog_templates_dir / "blueprints" / "wt" / "fix-tests.yml"
        expected_content = expected_file.read_text(encoding="utf-8")

        result = catalog_show_command(context, template_name)

        assert result.item is None
        assert result.content == expected_content
        assert result.template_matches == [("blueprints/wt/fix-tests.yml", expected_content)]
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    def test_catalog_show_missing_returns_not_found(self, isolated_workspace: Path) -> None:
        """catalog_show_command returns error when template is not found."""
        context = _make_context(isolated_workspace)

        result = catalog_show_command(context, "non-existent")

        assert result.item is None
        assert result.content is None
        assert result.template_matches == []
        assert result.errors == ["Catalog blueprint or template 'non-existent' not found."]
        assert result.warnings == []
        assert result.fixes == []


class CatalogShowCliIntegrationTests:
    """Typer runner integration tests for wt catalog show."""

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("fix-tests", id="bare-name"),
            pytest.param("wt/fix-tests", id="namespaced-name"),
        ],
    )
    def test_catalog_show_cli_renders_terminal(
        self, cli_runner: CliRunner, isolated_workspace: Path, template_name: str
    ) -> None:
        """wt catalog show renders terminal output and exits 0."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "show", template_name],
        )

        assert result.exit_code == 0
        assert "Template:" in result.stdout

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("fix-tests", id="bare-name"),
            pytest.param("wt/fix-tests", id="namespaced-name"),
        ],
    )
    def test_catalog_show_cli_renders_json(
        self, cli_runner: CliRunner, isolated_workspace: Path, template_name: str
    ) -> None:
        """wt catalog show --format json emits valid CatalogShowResult event."""
        expected_file = Filesystem().catalog_templates_dir / "blueprints" / "wt" / "fix-tests.yml"
        expected_content = expected_file.read_text(encoding="utf-8")

        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "show", template_name, "--format", "json"],
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "CatalogShowResult",
            "payload": {
                "item": None,
                "content": expected_content,
                "template_matches": [{"item_type": "template", "path": "blueprints/wt/fix-tests.yml"}],
                "catalog_path_relative": None,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }

    def test_catalog_show_cli_missing_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt catalog show on missing template exits 1."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "show", "missing"],
        )

        assert result.exit_code == 1
        assert "not found" in result.stdout
