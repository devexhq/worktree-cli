"""Unit tests for catalog CLI commands and Rich formatters."""

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem
from worktree.cli import app
from worktree.cli.catalog.commands.catalog_create import catalog_create_command
from worktree.cli.catalog.commands.catalog_delete import catalog_delete_command
from worktree.cli.catalog.commands.catalog_list import catalog_list_command
from worktree.cli.catalog.commands.catalog_show import catalog_show_command
from worktree.cli.catalog.renderers import build_catalog_table
from worktree.core.catalog.services.inventory import create_catalog_item
from worktree.core.context import get_cli_context
from worktree.core.db import CatalogItemType, CatalogRecord

runner = CliRunner()


def test_build_catalog_table_columns(fs: FileSystem) -> None:
    item = CatalogRecord(
        id=1,
        sha="workflow_1234567",
        item_type=CatalogItemType.WORKFLOW,
        name="test-wf",
        path=fs.base_path / "workflows" / "test-wf.yml",
        checksum="1234567890abcdef",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
    )
    table = build_catalog_table([item])
    columns = [col.header for col in table.columns]
    assert columns == ["Name", "Type", "Path", "SHA"]


def test_catalog_list_command_empty(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    outcome = catalog_list_command(cli_ctx=get_cli_context(cwd=fs.base_path))
    assert outcome.ok
    assert len(outcome.items) == 0


def test_catalog_create_command_and_list_filtering(fs: FileSystem) -> None:
    cli_ctx = get_cli_context(cwd=fs.base_path)
    create_res1 = catalog_create_command("workflow", name="wf-1", cli_ctx=cli_ctx)
    assert create_res1.ok
    assert create_res1.item is not None
    assert create_res1.item.item_type == CatalogItemType.WORKFLOW

    create_res2 = catalog_create_command("task", name="task-1", cli_ctx=cli_ctx)
    assert create_res2.ok

    # List all
    list_all = catalog_list_command(cli_ctx=cli_ctx)
    assert list_all.ok
    assert len(list_all.items) == 2

    # Filter workflow
    list_wf = catalog_list_command(type_filter="workflow", cli_ctx=cli_ctx)
    assert list_wf.ok
    assert len(list_wf.items) == 1
    assert list_wf.items[0].name == "wf-1"

    # Filter task
    list_task = catalog_list_command(type_filter=CatalogItemType.TASK, cli_ctx=cli_ctx)
    assert list_task.ok
    assert len(list_task.items) == 1
    assert list_task.items[0].name == "task-1"

    # Filter invalid type
    list_invalid = catalog_list_command(type_filter="invalid_type", cli_ctx=cli_ctx)
    assert not list_invalid.ok
    assert "Invalid --type" in list_invalid.errors[0]


def test_catalog_create_collision_returns_error(fs: FileSystem) -> None:
    cli_ctx = get_cli_context(cwd=fs.base_path)
    res1 = catalog_create_command("step", name="step-1", cli_ctx=cli_ctx)
    assert res1.ok

    res2 = catalog_create_command("step", name="step-1", cli_ctx=cli_ctx)
    assert not res2.ok
    assert "collision" in res2.errors[0]


def test_catalog_show_command(fs: FileSystem) -> None:
    create_catalog_item("workflow", "show-wf", cwd=fs.base_path)
    cli_ctx = get_cli_context(cwd=fs.base_path)

    # Show by name
    show_name = catalog_show_command("show-wf", cli_ctx=cli_ctx)
    assert show_name.ok
    assert show_name.item is not None
    assert show_name.item.sha is not None
    assert show_name.content is not None
    assert "show-wf" in show_name.content

    # Show by SHA
    show_sha = catalog_show_command(show_name.item.sha, cli_ctx=cli_ctx)
    assert show_sha.ok
    assert show_sha.item is not None

    # Show missing
    show_missing = catalog_show_command("missing-item", cli_ctx=cli_ctx)
    assert not show_missing.ok
    assert "not found" in show_missing.errors[0]


def test_catalog_list_type_template(fs: FileSystem) -> None:
    cli_ctx = get_cli_context(cwd=fs.base_path)
    outcome = catalog_list_command(type_filter="template", cli_ctx=cli_ctx)
    assert outcome.ok
    assert outcome.items == []


def test_catalog_show_packaged_template_fallback(fs: FileSystem) -> None:
    cli_ctx = get_cli_context(cwd=fs.base_path)
    show_fix = catalog_show_command("fix-tests", cli_ctx=cli_ctx)
    assert show_fix.ok
    assert show_fix.item is None
    assert show_fix.content is not None
    assert "fix-tests" in show_fix.content

    show_default = catalog_show_command("default", cli_ctx=cli_ctx)
    assert show_default.ok
    assert show_default.content is not None


def test_cli_catalog_list_type_template(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    res = runner.invoke(app, ["catalog", "list", "--type", "template"])
    assert res.exit_code == 0
    assert "workflows/default.yml" in res.output
    assert "tasks/default.yml" in res.output
    assert "steps/default.yml" in res.output


def test_cli_catalog_show_template_fallback(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    res = runner.invoke(app, ["catalog", "show", "fix-tests"])
    assert res.exit_code == 0
    assert "fix-tests" in res.output

    res_missing = runner.invoke(app, ["catalog", "show", "no-such-name"])
    assert res_missing.exit_code == 1
    assert "Catalog blueprint or template 'no-such-name' not found" in res_missing.output


def test_catalog_delete_command(fs: FileSystem) -> None:
    item = create_catalog_item("task", "del-task", cwd=fs.base_path)
    cli_ctx = get_cli_context(cwd=fs.base_path)

    del_res = catalog_delete_command(item.sha, force=True, cli_ctx=cli_ctx)
    assert del_res.ok
    assert del_res.deleted

    del_missing = catalog_delete_command(item.sha, force=True, cli_ctx=cli_ctx)
    assert not del_missing.ok
    assert not del_missing.deleted


def test_catalog_delete_command_confirmation(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    item1 = create_catalog_item("task", "del-task-1", cwd=fs.base_path)
    cli_ctx = get_cli_context(cwd=fs.base_path)
    monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: True)
    res_confirmed = catalog_delete_command(item1.sha, force=False, cli_ctx=cli_ctx)
    assert res_confirmed.ok
    assert res_confirmed.deleted

    item2 = create_catalog_item("task", "del-task-2", cwd=fs.base_path)
    monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)
    res_cancelled = catalog_delete_command(item2.sha, force=False, cli_ctx=cli_ctx)
    assert not res_cancelled.ok
    assert not res_cancelled.deleted
    assert "cancelled" in res_cancelled.errors[0]

    def _raise_abort(*args: object, **kwargs: object) -> bool:
        import typer

        raise typer.Abort()

    monkeypatch.setattr("typer.confirm", _raise_abort)
    res_abort = catalog_delete_command(item2.sha, force=False, cli_ctx=cli_ctx)
    assert not res_abort.ok
    assert not res_abort.deleted


def test_cli_wt_catalog_runner(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)

    # wt catalog create workflow --name cli-wf
    res_create = runner.invoke(app, ["catalog", "create", "workflow", "--name", "cli-wf"])
    assert res_create.exit_code == 0
    assert "Created catalog blueprint" in res_create.output

    # wt catalog list
    res_list = runner.invoke(app, ["catalog", "list"])
    assert res_list.exit_code == 0
    assert "cli-wf" in res_list.output
    assert "Catalog Blueprints:" in res_list.output
    assert "Name" in res_list.output
    assert "Type" in res_list.output
    assert "Path" in res_list.output
    assert "SHA" in res_list.output

    # wt catalog list --type workflow
    res_list_wf = runner.invoke(app, ["catalog", "list", "--type", "workflow"])
    assert res_list_wf.exit_code == 0
    assert "cli-wf" in res_list_wf.output

    # wt catalog show cli-wf
    res_show = runner.invoke(app, ["catalog", "show", "cli-wf"])
    assert res_show.exit_code == 0
    assert "Blueprint:" in res_show.output

    # wt catalog delete cli-wf without force (interactive decline)
    res_del_decline = runner.invoke(app, ["catalog", "delete", "cli-wf"], input="n\n")
    assert res_del_decline.exit_code == 1
    assert "Deletion cancelled" in res_del_decline.output

    # wt catalog delete cli-wf --force
    res_del = runner.invoke(app, ["catalog", "delete", "cli-wf", "--force"])
    assert res_del.exit_code == 0
    assert "Deleted catalog blueprint" in res_del.output

    # wt catalog delete non-existent
    res_del_fail = runner.invoke(app, ["catalog", "delete", "non-existent", "--force"])
    assert res_del_fail.exit_code == 1
