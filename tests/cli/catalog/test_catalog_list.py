"""Dual-tier matrix tests for wt catalog list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_list import catalog_list_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogListResult
from worktree.core.config.generator import build_default_config
from worktree.core.db import CatalogItemType, CatalogRecord
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


class CatalogListRootTests:
    """Direct handler unit tests for catalog_list_command."""

    def test_catalog_list_returns_records(self, isolated_workspace: Path) -> None:
        """catalog_list_command returns all indexed catalog records."""
        context = _make_context(isolated_workspace)
        create_result = catalog_create_command(context, "blueprint", name="cli-blueprint")
        if create_result.item is None:
            pytest.fail("Failed to scaffold blueprint")

        result = catalog_list_command(context)

        assert_model_equal(
            result,
            CatalogListResult(
                items=[_fully_set(create_result.item)],
                type_filter=None,
                templates=[],
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        ("type_filter", "expected_type", "expected_name"),
        [
            pytest.param("blueprint", CatalogItemType.BLUEPRINT, "blueprint-item", id="filter-blueprint"),
            pytest.param("step", CatalogItemType.STEP, "step-item", id="filter-step"),
        ],
    )
    def test_catalog_list_filters_by_type(
        self,
        isolated_workspace: Path,
        type_filter: str,
        expected_type: CatalogItemType,
        expected_name: str,
    ) -> None:
        """catalog_list_command filters items by type."""
        context = _make_context(isolated_workspace)
        blueprint_result = catalog_create_command(context, "blueprint", name="blueprint-item")
        step_result = catalog_create_command(context, "step", name="step-item")
        expected_item = blueprint_result.item if expected_type == CatalogItemType.BLUEPRINT else step_result.item
        if expected_item is None:
            pytest.fail("Expected item was not created")

        result = catalog_list_command(context, type_filter=type_filter)

        assert_model_equal(
            result,
            CatalogListResult(
                items=[_fully_set(expected_item)],
                type_filter=expected_type,
                templates=[],
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_catalog_list_type_template_returns_bundled_templates(self, isolated_workspace: Path) -> None:
        """catalog_list_command returns packaged starter templates when type is template."""
        context = _make_context(isolated_workspace)

        result = catalog_list_command(context, type_filter="template")

        assert_model_equal(
            result,
            CatalogListResult(
                items=[],
                type_filter="template",
                templates=Catalog.list_packaged_templates(),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        "invalid_type",
        [
            pytest.param("invalid_type", id="unknown-string"),
            pytest.param("workflow", id="non-catalog-type"),
        ],
    )
    def test_catalog_list_invalid_type_returns_error(self, isolated_workspace: Path, invalid_type: str) -> None:
        """catalog_list_command returns error when type is invalid."""
        context = _make_context(isolated_workspace)

        result = catalog_list_command(context, type_filter=invalid_type)

        assert_model_equal(
            result,
            CatalogListResult(
                items=[],
                type_filter=None,
                templates=[],
                errors=[f"Invalid --type argument '{invalid_type}'. Allowed choices: blueprint, step"],
                warnings=[],
                fixes=[],
            ),
        )


class CatalogListCliIntegrationTests:
    """Typer runner integration tests for wt catalog list."""

    @pytest.mark.parametrize(
        "subcommand_args",
        [
            pytest.param(["catalog"], id="group-default"),
            pytest.param(["catalog", "list"], id="explicit-subcommand"),
        ],
    )
    def test_catalog_list_cli_renders_terminal_table(
        self, cli_runner: CliRunner, isolated_workspace: Path, subcommand_args: list[str]
    ) -> None:
        """wt catalog list renders terminal table and exits 0."""
        Catalog(isolated_workspace).create(CatalogItemType.BLUEPRINT, "listed-blueprint")

        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), *subcommand_args],
        )

        assert result.exit_code == 0
        assert "Catalog Blueprints" in result.stdout

    @pytest.mark.parametrize(
        "subcommand_args",
        [
            pytest.param(["catalog", "--format", "json"], id="group-default"),
            pytest.param(["catalog", "list", "--format", "json"], id="explicit-subcommand"),
        ],
    )
    def test_catalog_list_cli_renders_json(
        self, cli_runner: CliRunner, isolated_workspace: Path, subcommand_args: list[str]
    ) -> None:
        """wt catalog list --format json emits valid CatalogListResult event."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), *subcommand_args],
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "CatalogListResult",
            "payload": {
                "items": [],
                "type_filter": None,
                "templates": [],
                "total_items": 0,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }

    def test_catalog_list_cli_invalid_type_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt catalog list --type invalid exits 1."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "list", "--type", "bad"],
        )

        assert result.exit_code == 1
        assert "Invalid --type argument" in result.stdout
