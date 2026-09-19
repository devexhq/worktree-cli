"""Dual-tier matrix tests for wt catalog show."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_show import catalog_show_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.catalog.models import CatalogShowResult
from worktree.core.config.generator import build_default_config
from worktree.core.db import CatalogRecord
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


def _fully_set(record: CatalogRecord) -> CatalogRecord:
    """Rebuild a live CatalogRecord so every field, including the DB-assigned id, is named.

    The repository sets `id` via attribute assignment after insert, which pydantic does not
    record in `model_fields_set`. assert_model_equal requires an expected object to name every
    field, so reusing a live record as `expected` needs this rebuild first.

    `updated_at` is replaced with a matcher: every read command (list/show/delete) reindexes the
    catalog via `scan_and_index_catalog`, and `CatalogRepository.upsert` unconditionally bumps
    `updated_at` on each reindex even when content is unchanged, so the value on the record
    returned by create() is stale by the time a later command re-reads it.
    """
    return CatalogRecord.model_construct(
        id=record.id,
        key=record.key,
        sha=record.sha,
        item_type=record.item_type,
        name=record.name,
        namespace=record.namespace,
        path=record.path,
        checksum=record.checksum,
        created_at=record.created_at,
        updated_at=ANY_TIMESTAMP,
    )


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

        assert_model_equal(
            result,
            CatalogShowResult(
                item=_fully_set(create_result.item),
                content=expected_content,
                template_matches=[],
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

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

        assert_model_equal(
            result,
            CatalogShowResult(
                item=None,
                content=expected_content,
                template_matches=[("blueprints/wt/fix-tests.yml", expected_content)],
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_catalog_show_missing_returns_not_found(self, isolated_workspace: Path) -> None:
        """catalog_show_command returns error when template is not found."""
        context = _make_context(isolated_workspace)

        result = catalog_show_command(context, "non-existent")

        assert_model_equal(
            result,
            CatalogShowResult(
                item=None,
                content=None,
                template_matches=[],
                errors=["Catalog blueprint or template 'non-existent' not found."],
                warnings=[],
                fixes=[],
            ),
        )


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
