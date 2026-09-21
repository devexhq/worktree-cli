"""Dual-tier matrix tests for wt catalog delete."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_delete import catalog_delete_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogDeleteResult
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


class CatalogDeleteRootTests:
    """Direct handler unit tests for catalog_delete_command."""

    @pytest.mark.parametrize(
        ("item_type_str", "name", "rel_path"),
        [
            pytest.param("blueprint", "del-blueprint", Path("blueprints/del-blueprint.yml"), id="blueprint"),
            pytest.param("step", "del-step", Path("steps/del-step.yml"), id="step"),
        ],
    )
    def test_catalog_delete_with_force_deletes_item(
        self,
        isolated_workspace: Path,
        item_type_str: str,
        name: str,
        rel_path: Path,
    ) -> None:
        """catalog_delete_command deletes item when force is True."""
        context = _make_context(isolated_workspace)
        create_result = catalog_create_command(context, item_type_str, name=name)
        if create_result.item is None:
            pytest.fail("Failed to scaffold blueprint")

        target_file = isolated_workspace / ".worktree" / "catalog" / rel_path
        assert target_file.is_file()

        result = catalog_delete_command(context, name, force=True)

        assert not target_file.exists()
        assert_model_equal(
            result,
            CatalogDeleteResult(
                item=_fully_set(create_result.item),
                deleted=True,
                cancelled=False,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_catalog_delete_unconfirmed_cancels(
        self, isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """catalog_delete_command cancels when confirmation is declined."""
        context = _make_context(isolated_workspace)
        catalog_create_command(context, "blueprint", name="del-blueprint")

        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)

        result = catalog_delete_command(context, "del-blueprint", force=False)

        assert (isolated_workspace / ".worktree" / "catalog" / "blueprints" / "del-blueprint.yml").is_file()
        assert_model_equal(
            result,
            CatalogDeleteResult(
                item=None,
                deleted=False,
                cancelled=True,
                errors=["Deletion cancelled."],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("wt/starter-task", id="starter-task"),
            pytest.param("wt/fix-tests", id="fix-tests"),
        ],
    )
    def test_catalog_delete_bundled_template_rejected(self, isolated_workspace: Path, template_name: str) -> None:
        """catalog_delete_command rejects deletion of templates in wt/ namespace."""
        context = _make_context(isolated_workspace)

        result = catalog_delete_command(context, template_name, force=True)

        assert_model_equal(
            result,
            CatalogDeleteResult(
                item=None,
                deleted=False,
                cancelled=False,
                errors=[f"Cannot delete bundled catalog template '{template_name}'."],
                warnings=[],
                fixes=[],
            ),
        )

    def test_catalog_delete_missing_returns_not_found(self, isolated_workspace: Path) -> None:
        """catalog_delete_command returns error on missing template."""
        context = _make_context(isolated_workspace)

        result = catalog_delete_command(context, "missing-blueprint", force=True)

        assert_model_equal(
            result,
            CatalogDeleteResult(
                item=None,
                deleted=False,
                cancelled=False,
                errors=["Catalog blueprint 'missing-blueprint' not found."],
                warnings=[],
                fixes=[],
            ),
        )


class CatalogDeleteCliIntegrationTests:
    """Typer runner integration tests for wt catalog delete."""

    @pytest.mark.parametrize(
        ("item_type_enum", "name"),
        [
            pytest.param(CatalogItemType.BLUEPRINT, "del-cli-blueprint", id="blueprint"),
            pytest.param(CatalogItemType.STEP, "del-cli-step", id="step"),
        ],
    )
    def test_catalog_delete_cli_with_force_exits_zero(
        self,
        cli_runner: CliRunner,
        isolated_workspace: Path,
        item_type_enum: CatalogItemType,
        name: str,
    ) -> None:
        """wt catalog delete --force deletes item and exits 0."""
        Catalog(isolated_workspace).create(item_type_enum, name)

        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "delete", name, "--force"],
        )

        assert result.exit_code == 0
        assert "Deleted catalog blueprint" in result.stdout

    def test_catalog_delete_cli_confirmation_declined_exits_one(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """wt catalog delete with 'n' response cancels and exits 1."""
        Catalog(isolated_workspace).create(CatalogItemType.BLUEPRINT, "del-declined-blueprint")

        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "delete", "del-declined-blueprint"],
            input="n\n",
        )

        assert result.exit_code == 1
        assert "Deletion cancelled" in result.stdout

    def test_catalog_delete_cli_renders_json(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt catalog delete --force --format json emits valid CatalogDeleteResult event."""
        create_result = Catalog(isolated_workspace).create(CatalogItemType.BLUEPRINT, "del-json-blueprint")
        if create_result.item is None:
            pytest.fail("Failed to scaffold blueprint")

        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "delete", "del-json-blueprint", "--force", "--format", "json"],
        )

        assert result.exit_code == 0
        actual_json = json.loads(result.stdout)
        assert actual_json["payload"]["item"]["created_at"] != ""
        assert actual_json["payload"]["item"]["updated_at"] != ""
        actual_json["payload"]["item"]["created_at"] = "placeholder"
        actual_json["payload"]["item"]["updated_at"] = "placeholder"

        assert actual_json == {
            "event_type": "CatalogDeleteResult",
            "payload": {
                "item": {
                    "id": create_result.item.id,
                    "key": "del-json-blueprint",
                    "sha": create_result.item.sha,
                    "item_type": "blueprint",
                    "name": "del-json-blueprint",
                    "namespace": None,
                    "path": "blueprints/del-json-blueprint.yml",
                    "checksum": create_result.item.checksum,
                    "created_at": "placeholder",
                    "updated_at": "placeholder",
                },
                "deleted": True,
                "cancelled": False,
                "errors": [],
                "warnings": [],
                "fixes": [],
                "error_code": None,
            },
        }

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("wt/starter-task", id="starter-task"),
            pytest.param("wt/fix-tests", id="fix-tests"),
        ],
    )
    def test_catalog_delete_cli_bundled_template_exits_one(
        self, cli_runner: CliRunner, isolated_workspace: Path, template_name: str
    ) -> None:
        """wt catalog delete <template> --force exits 1."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "delete", template_name, "--force"],
        )

        assert result.exit_code == 1
        assert "Cannot delete bundled catalog template" in result.stdout

    def test_catalog_delete_cli_missing_exits_one(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """wt catalog delete missing-blueprint --force exits 1."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "delete", "missing-blueprint", "--force"],
        )

        assert result.exit_code == 1
        assert "not found" in result.stdout
