"""Tier 3 CLI integration tests for wt catalog validate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from tests.harness.catalog import write_runnable_blueprint
from worktree.cli import app
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config


@pytest.fixture(autouse=True)
def _setup_workspace_config(isolated_workspace: Path) -> None:
    """Ensure workspace contains valid config.json for CLI context resolution."""
    config_path = isolated_workspace / ".worktree" / "config.json"
    payload = build_default_config("demo-workspace")
    Filesystem.atomic_write_json(config_path, payload)


class CatalogValidateCliIntegrationTests:
    """Typer runner integration tests for wt catalog validate."""

    def test_catalog_validate_valid_blueprint_exits_zero(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """[tier-3/integration] wt catalog validate: indexed valid blueprint exits 0."""
        write_runnable_blueprint(isolated_workspace, key="cli-flow", steps=[{"id": "s1", "run": "echo hi"}])

        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "catalog", "validate", "cli-flow"])

        assert result.exit_code == 0
        assert "PASSED" in result.stdout

    def test_catalog_validate_invalid_blueprint_exits_one(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """[tier-3/integration] wt catalog validate --type blueprint: schema-invalid blueprint file path exits 1."""
        invalid_path = isolated_workspace / "invalid.yml"
        invalid_path.write_text(yaml.safe_dump({"timeout_seconds": -1}), encoding="utf-8")

        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "catalog", "validate", "invalid.yml", "--type", "blueprint"]
        )

        assert result.exit_code == 1
        assert "CATALOG_SCHEMA_INVALID" in result.stdout

    def test_catalog_validate_unknown_name_exits_two(self, cli_runner: CliRunner, isolated_workspace: Path) -> None:
        """[tier-3/integration] wt catalog validate: unmatched catalog name exits 2."""
        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "catalog", "validate", "does-not-exist"])

        assert result.exit_code == 2
        assert "CATALOG_ITEM_NOT_FOUND" in result.stdout

    def test_catalog_validate_file_target_without_type_exits_two(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """[tier-3/integration] wt catalog validate: existing file target with no --type exits 2, output names CATALOG_TYPE_REQUIRED."""
        draft_path = isolated_workspace / "draft.yml"
        draft_path.write_text(yaml.safe_dump({"name": "draft"}), encoding="utf-8")

        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "catalog", "validate", "draft.yml"])

        assert result.exit_code == 2
        assert "CATALOG_TYPE_REQUIRED" in result.stdout

    def test_catalog_validate_invalid_type_value_rejected_by_click(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """[tier-3/integration] wt catalog validate --type banana: rejected by Click's own choice validation, non-zero exit."""
        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "catalog", "validate", "whatever.yml", "--type", "banana"]
        )

        assert result.exit_code == 2
        assert "'--type'" in result.output

    def test_catalog_validate_format_json_matches_wire_schema(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """[tier-3/integration] wt catalog validate --format json: payload has exactly status/valid/status_label/target/resolved_path/item_type/errors/warnings/fixes keys."""
        write_runnable_blueprint(isolated_workspace, key="json-flow", steps=[{"id": "s1", "run": "echo hi"}])

        result = cli_runner.invoke(
            app, ["-p", str(isolated_workspace), "catalog", "validate", "json-flow", "--format", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["event_type"] == "CatalogValidateResult"
        assert set(payload["payload"]) == {
            "status",
            "valid",
            "status_label",
            "target",
            "resolved_path",
            "item_type",
            "errors",
            "warnings",
            "fixes",
        }
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["valid"] is True

    def test_catalog_validate_missing_target_argument_errors(
        self, cli_runner: CliRunner, isolated_workspace: Path
    ) -> None:
        """[tier-3/integration] wt catalog validate: omitted target argument exits non-zero."""
        result = cli_runner.invoke(app, ["-p", str(isolated_workspace), "catalog", "validate"])

        assert result.exit_code == 2
        assert "'target'" in result.output
