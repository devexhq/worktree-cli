"""Unit tests for catalog CLI commands and Rich formatters."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, make_cli_context
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_delete import catalog_delete_command
from worktree.cli.catalog.commands.catalog_list import catalog_list_command
from worktree.cli.catalog.commands.catalog_show import catalog_show_command
from worktree.core.catalog.services.inventory import create_catalog_item
from worktree.core.db import CatalogItemType

runner = CliRunner()


class CatalogCommandDirectTests:
    """Direct unit tests for catalog command handlers."""

    def test_catalog_list_command_empty(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(fs.base_path)
        outcome = catalog_list_command(make_cli_context(cwd=fs.base_path))
        assert outcome.ok
        assert len(outcome.items) == 0

    def test_catalog_create_command_and_list_filtering(self, fs: FileSystem) -> None:
        cli_ctx = make_cli_context(cwd=fs.base_path)
        create_res1 = catalog_create_command(cli_ctx, "blueprint", name="bp-1")
        assert create_res1.ok
        assert create_res1.item is not None
        assert create_res1.item.item_type == CatalogItemType.BLUEPRINT

        create_res2 = catalog_create_command(cli_ctx, "step", name="step-1")
        assert create_res2.ok

        # List all
        list_all = catalog_list_command(cli_ctx)
        assert list_all.ok
        assert len(list_all.items) == 2

        list_blueprint = catalog_list_command(cli_ctx, type_filter="blueprint")
        assert list_blueprint.ok
        assert len(list_blueprint.items) == 1
        assert list_blueprint.items[0].name == "bp-1"

        list_step = catalog_list_command(cli_ctx, type_filter=CatalogItemType.STEP)
        assert list_step.ok
        assert len(list_step.items) == 1
        assert list_step.items[0].path.as_posix() == "steps/step-1.yml"

        # Filter invalid type
        list_invalid = catalog_list_command(cli_ctx, type_filter="invalid_type")
        assert not list_invalid.ok
        assert "Invalid --type" in list_invalid.errors[0]

    def test_catalog_create_collision_returns_error(self, fs: FileSystem) -> None:
        cli_ctx = make_cli_context(cwd=fs.base_path)
        res1 = catalog_create_command(cli_ctx, "step", name="step-1")
        assert res1.ok

        res2 = catalog_create_command(cli_ctx, "step", name="step-1")
        assert not res2.ok
        assert "collision" in res2.errors[0]

    def test_catalog_show_command(self, fs: FileSystem) -> None:
        create_catalog_item("blueprint", "show-bp", path=fs.base_path)
        cli_ctx = make_cli_context(cwd=fs.base_path)

        # Show by name
        show_name = catalog_show_command(cli_ctx, "show-bp")
        assert show_name.ok
        assert show_name.item is not None
        assert show_name.item.sha is not None
        assert show_name.content is not None
        assert "show-bp" in show_name.content

        # Show by SHA
        show_sha = catalog_show_command(cli_ctx, show_name.item.sha)
        assert show_sha.ok
        assert show_sha.item is not None

        # Show missing
        show_missing = catalog_show_command(cli_ctx, "missing-item")
        assert not show_missing.ok
        assert "not found" in show_missing.errors[0]

    def test_catalog_list_type_template(self, fs: FileSystem) -> None:
        cli_ctx = make_cli_context(cwd=fs.base_path)
        outcome = catalog_list_command(cli_ctx, type_filter="template")
        assert outcome.ok
        assert outcome.items == []

    def test_catalog_show_packaged_template_fallback(self, fs: FileSystem) -> None:
        cli_ctx = make_cli_context(cwd=fs.base_path)
        show_fix = catalog_show_command(cli_ctx, "fix-tests")
        assert show_fix.ok
        assert show_fix.item is None
        assert show_fix.content is not None
        assert "fix-tests" in show_fix.content

        show_default = catalog_show_command(cli_ctx, "default")
        assert show_default.ok
        assert show_default.content is not None

    def test_catalog_delete_command(self, fs: FileSystem) -> None:
        item = create_catalog_item("blueprint", "del-blueprint", path=fs.base_path)
        cli_ctx = make_cli_context(cwd=fs.base_path)

        del_res = catalog_delete_command(cli_ctx, item.sha, force=True)
        assert del_res.ok
        assert del_res.deleted

        del_missing = catalog_delete_command(cli_ctx, item.sha, force=True)
        assert not del_missing.ok
        assert not del_missing.deleted

    def test_catalog_delete_command_confirmation(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        item1 = create_catalog_item("blueprint", "del-blueprint-1", path=fs.base_path)
        cli_ctx = make_cli_context(cwd=fs.base_path)
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: True)
        res_confirmed = catalog_delete_command(cli_ctx, item1.sha, force=False)
        assert res_confirmed.ok
        assert res_confirmed.deleted

        item2 = create_catalog_item("blueprint", "del-blueprint-2", path=fs.base_path)
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)
        res_cancelled = catalog_delete_command(cli_ctx, item2.sha, force=False)
        assert not res_cancelled.ok
        assert not res_cancelled.deleted
        assert "cancelled" in res_cancelled.errors[0]

        def _raise_abort(*args: object, **kwargs: object) -> bool:
            import typer

            raise typer.Abort()

        monkeypatch.setattr("typer.confirm", _raise_abort)
        res_abort = catalog_delete_command(cli_ctx, item2.sha, force=False)
        assert not res_abort.ok
        assert not res_abort.deleted


class CatalogCliTests:
    """Integration CLI invocation tests for wt catalog commands."""

    def test_cli_catalog_list_type_template(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        res = runner.invoke(app, ["catalog", "list", "--type", "template"])
        assert res.exit_code == 0
        assert "blueprints/default.yml" in res.output
        assert "steps/default.yml" in res.output

    def test_cli_catalog_show_template_fallback(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        res = runner.invoke(app, ["catalog", "show", "fix-tests"])
        assert res.exit_code == 0
        assert "fix-tests" in res.output

        res_missing = runner.invoke(app, ["catalog", "show", "no-such-name"])
        assert res_missing.exit_code == 1
        assert "Catalog blueprint or template 'no-such-name' not found" in res_missing.output

    def test_cli_wt_catalog_runner(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        res_create = runner.invoke(app, ["catalog", "create", "blueprint", "--name", "cli-blueprint"])
        assert res_create.exit_code == 0
        assert "Created catalog blueprint" in res_create.output

        res_list = runner.invoke(app, ["catalog", "list"])
        assert res_list.exit_code == 0
        assert "cli-blueprint" in res_list.output
        assert "Catalog Blueprints:" in res_list.output
        assert "Name" in res_list.output
        assert "Type" in res_list.output
        assert "Path" in res_list.output
        assert "SHA" in res_list.output

        res_list_blueprint = runner.invoke(app, ["catalog", "list", "--type", "blueprint"])
        assert res_list_blueprint.exit_code == 0
        assert "cli-blueprint" in res_list_blueprint.output

        res_show = runner.invoke(app, ["catalog", "show", "cli-blueprint"])
        assert res_show.exit_code == 0
        assert "Blueprint:" in res_show.output

        res_del_decline = runner.invoke(app, ["catalog", "delete", "cli-blueprint"], input="n\n")
        assert res_del_decline.exit_code == 1
        assert "Deletion cancelled" in res_del_decline.output

        res_del = runner.invoke(app, ["catalog", "delete", "cli-blueprint", "--force"])
        assert res_del.exit_code == 0
        assert "Deleted catalog blueprint" in res_del.output

        res_del_fail = runner.invoke(app, ["catalog", "delete", "non-existent", "--force"])
        assert res_del_fail.exit_code == 1

    def test_cli_catalog_commands_json_format(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        import json

        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        res_create = runner.invoke(
            app, ["catalog", "create", "blueprint", "--name", "json-blueprint", "--format", "json"]
        )
        assert res_create.exit_code == 0
        lines = [line for line in res_create.output.strip().split("\n") if line]
        payload = json.loads(lines[-1])
        assert payload["event_type"] == "CatalogCreateResult"
        assert payload["payload"]["item"]["name"] == "json-blueprint"

        res_list = runner.invoke(app, ["catalog", "list", "--format", "json"])
        assert res_list.exit_code == 0
        lines = [line for line in res_list.output.strip().split("\n") if line]
        payload = json.loads(lines[-1])
        assert payload["event_type"] == "CatalogListResult"
        assert len(payload["payload"]["items"]) == 1
        assert payload["payload"]["items"][0]["name"] == "json-blueprint"

        res_show = runner.invoke(app, ["catalog", "show", "json-blueprint", "--format", "json"])
        assert res_show.exit_code == 0
        lines = [line for line in res_show.output.strip().split("\n") if line]
        payload = json.loads(lines[-1])
        assert payload["event_type"] == "CatalogShowResult"
        assert payload["payload"]["item"]["name"] == "json-blueprint"

        res_del = runner.invoke(app, ["catalog", "delete", "json-blueprint", "--force", "--format", "json"])
        assert res_del.exit_code == 0
        lines = [line for line in res_del.output.strip().split("\n") if line]
        payload = json.loads(lines[-1])
        assert payload["event_type"] == "CatalogDeleteResult"
        assert payload["payload"]["deleted"] is True
