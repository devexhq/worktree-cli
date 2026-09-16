"""Dual-tier matrix tests for catalog CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_delete import catalog_delete_command
from worktree.cli.catalog.commands.catalog_list import catalog_list_command
from worktree.cli.catalog.commands.catalog_show import catalog_show_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
)
from worktree.core.catalog.services.inventory import compute_catalog_sha
from worktree.core.config.generator import build_default_config
from worktree.core.db import CatalogItemType, CatalogRecord
from worktree.core.db.facade import WorktreeDb

pytestmark = pytest.mark.cli


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


# --------------------------------------------------------------------------- #
# Catalog List Tests                                                          #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Catalog Show Tests                                                          #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Catalog Create Tests                                                        #
# --------------------------------------------------------------------------- #


class CatalogCreateRootTests:
    """Direct handler unit tests for catalog_create_command."""

    @pytest.mark.parametrize(
        ("item_type_str", "item_type_enum", "name", "rel_path"),
        [
            pytest.param(
                "blueprint",
                CatalogItemType.BLUEPRINT,
                "cli-blueprint",
                Path("blueprints/cli-blueprint.yml"),
                id="blueprint",
            ),
            pytest.param(
                "step",
                CatalogItemType.STEP,
                "cli-step",
                Path("steps/cli-step.yml"),
                id="step",
            ),
        ],
    )
    def test_catalog_create_scaffolds_template_file_and_record(
        self,
        isolated_workspace: Path,
        item_type_str: str,
        item_type_enum: CatalogItemType,
        name: str,
        rel_path: Path,
    ) -> None:
        """catalog_create_command creates file and returns CatalogCreateResult."""
        context = _make_context(isolated_workspace)

        result = catalog_create_command(context, item_type_str, name=name)

        target_file = isolated_workspace / ".worktree" / "catalog" / rel_path
        assert target_file.is_file()

        content = target_file.read_text(encoding="utf-8")
        expected_sha, expected_checksum = compute_catalog_sha(item_type_enum, content)

        assert_model_equal(
            result,
            CatalogCreateResult(
                item=CatalogRecord.model_construct(
                    id=1,
                    key=name,
                    sha=expected_sha,
                    item_type=item_type_enum,
                    name=name,
                    namespace=None,
                    path=rel_path,
                    checksum=expected_checksum,
                    created_at=ANY_TIMESTAMP,
                    updated_at=ANY_TIMESTAMP,
                ),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        ("item_type_str", "name", "rel_path"),
        [
            pytest.param("blueprint", "cli-blueprint", "blueprints/cli-blueprint.yml", id="blueprint"),
            pytest.param("step", "cli-step", "steps/cli-step.yml", id="step"),
        ],
    )
    def test_catalog_create_collision_returns_error(
        self,
        isolated_workspace: Path,
        item_type_str: str,
        name: str,
        rel_path: str,
    ) -> None:
        """catalog_create_command rejects duplicate item names."""
        context = _make_context(isolated_workspace)
        catalog_create_command(context, item_type_str, name=name)

        result_collision = catalog_create_command(context, item_type_str, name=name)

        assert_model_equal(
            result_collision,
            CatalogCreateResult(
                item=None,
                errors=[f"Catalog blueprint collision at path '{rel_path}'"],
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
    def test_catalog_create_invalid_type_returns_error(self, isolated_workspace: Path, invalid_type: str) -> None:
        """catalog_create_command returns error when item_type is invalid."""
        context = _make_context(isolated_workspace)

        result = catalog_create_command(context, invalid_type, name="cli-blueprint")

        assert_model_equal(
            result,
            CatalogCreateResult(
                item=None,
                errors=[f"Invalid item_type '{invalid_type}'. Allowed choices: blueprint, step"],
                warnings=[],
                fixes=[],
            ),
        )


class CatalogCreateCliIntegrationTests:
    """Typer runner integration tests for wt catalog create."""

    @pytest.mark.parametrize(
        ("item_type_str", "name", "expected_type_badge"),
        [
            pytest.param("blueprint", "cli-blueprint", "type: blueprint", id="blueprint"),
            pytest.param("step", "cli-step", "type: step", id="step"),
        ],
    )
    def test_catalog_create_cli_creates_item_terminal(
        self,
        cli_runner: CliRunner,
        isolated_workspace: Path,
        item_type_str: str,
        name: str,
        expected_type_badge: str,
    ) -> None:
        """wt catalog create renders creation confirmation and exits 0."""
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "create", item_type_str, "--name", name],
        )

        assert result.exit_code == 0
        assert "Created catalog blueprint" in result.stdout
        assert expected_type_badge in result.stdout

    @pytest.mark.parametrize(
        ("item_type_str", "item_type_enum", "name", "rel_path"),
        [
            pytest.param(
                "blueprint", CatalogItemType.BLUEPRINT, "cli-blueprint", "blueprints/cli-blueprint.yml", id="blueprint"
            ),
            pytest.param("step", CatalogItemType.STEP, "cli-step", "steps/cli-step.yml", id="step"),
        ],
    )
    def test_catalog_create_cli_renders_json(
        self,
        cli_runner: CliRunner,
        isolated_workspace: Path,
        item_type_str: str,
        item_type_enum: CatalogItemType,
        name: str,
        rel_path: str,
    ) -> None:
        """wt catalog create --format json emits valid CatalogCreateResult event."""
        result = cli_runner.invoke(
            app,
            [
                "-p",
                str(isolated_workspace),
                "catalog",
                "create",
                item_type_str,
                "--name",
                name,
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0

        target_file = isolated_workspace / ".worktree" / "catalog" / rel_path
        content = target_file.read_text(encoding="utf-8")
        expected_sha, expected_checksum = compute_catalog_sha(item_type_enum, content)

        actual_json = json.loads(result.stdout)
        assert actual_json["payload"]["item"]["created_at"] != ""
        assert actual_json["payload"]["item"]["updated_at"] != ""
        actual_json["payload"]["item"]["created_at"] = "placeholder"
        actual_json["payload"]["item"]["updated_at"] = "placeholder"

        assert actual_json == {
            "event_type": "CatalogCreateResult",
            "payload": {
                "item": {
                    "id": 1,
                    "key": name,
                    "sha": expected_sha,
                    "item_type": item_type_str,
                    "name": name,
                    "namespace": None,
                    "path": rel_path,
                    "checksum": expected_checksum,
                    "created_at": "placeholder",
                    "updated_at": "placeholder",
                },
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }

    @pytest.mark.parametrize(
        ("item_type_str", "name"),
        [
            pytest.param("blueprint", "collide-blueprint", id="blueprint"),
            pytest.param("step", "collide-step", id="step"),
        ],
    )
    def test_catalog_create_cli_collision_exits_one(
        self,
        cli_runner: CliRunner,
        isolated_workspace: Path,
        item_type_str: str,
        name: str,
    ) -> None:
        """wt catalog create on existing name exits 1."""
        cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "create", item_type_str, "--name", name],
        )
        result = cli_runner.invoke(
            app,
            ["-p", str(isolated_workspace), "catalog", "create", item_type_str, "--name", name],
        )

        assert result.exit_code == 1
        assert "collision" in result.stdout


# --------------------------------------------------------------------------- #
# Catalog Delete Tests                                                        #
# --------------------------------------------------------------------------- #


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
