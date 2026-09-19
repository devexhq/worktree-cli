"""Dual-tier matrix tests for wt catalog create."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.core.catalog.models import CatalogCreateResult
from worktree.core.catalog.services.inventory import compute_catalog_sha
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
