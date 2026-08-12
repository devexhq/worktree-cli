"""Unit tests for catalog CLI commands and Rich formatters."""

import pytest
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.catalog.command import (
    catalog_create_command,
    catalog_delete_command,
    catalog_list_command,
    catalog_show_command,
)
from getworktree.core.catalog.services.inventory import create_catalog_item
from getworktree.core.db import CatalogItemType
from tests.helpers import FileSystem

runner = CliRunner()


def test_catalog_list_command_empty(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    outcome = catalog_list_command(cwd=fs.base_path)
    assert outcome.ok
    assert len(outcome.items) == 0


def test_catalog_create_command_and_list_filtering(fs: FileSystem) -> None:
    create_res1 = catalog_create_command("workflow", name="wf-1", cwd=fs.base_path)
    assert create_res1.ok
    assert create_res1.item is not None
    assert create_res1.item.item_type == CatalogItemType.WORKFLOW

    create_res2 = catalog_create_command("task", name="task-1", cwd=fs.base_path)
    assert create_res2.ok

    # List all
    list_all = catalog_list_command(cwd=fs.base_path)
    assert list_all.ok
    assert len(list_all.items) == 2

    # Filter workflow
    list_wf = catalog_list_command(type_filter="workflow", cwd=fs.base_path)
    assert list_wf.ok
    assert len(list_wf.items) == 1
    assert list_wf.items[0].name == "wf-1"

    # Filter task
    list_task = catalog_list_command(type_filter=CatalogItemType.TASK, cwd=fs.base_path)
    assert list_task.ok
    assert len(list_task.items) == 1
    assert list_task.items[0].name == "task-1"

    # Filter invalid type
    list_invalid = catalog_list_command(type_filter="invalid_type", cwd=fs.base_path)
    assert not list_invalid.ok
    assert "Invalid --type" in list_invalid.errors[0]


def test_catalog_create_collision_returns_error(fs: FileSystem) -> None:
    res1 = catalog_create_command("step", name="step-1", cwd=fs.base_path)
    assert res1.ok

    res2 = catalog_create_command("step", name="step-1", cwd=fs.base_path)
    assert not res2.ok
    assert "collision" in res2.errors[0]


def test_catalog_show_command(fs: FileSystem) -> None:
    item = create_catalog_item("workflow", "show-wf", cwd=fs.base_path)

    # Show by name
    show_name = catalog_show_command("show-wf", cwd=fs.base_path)
    assert show_name.ok
    assert show_name.item is not None
    assert show_name.item.sha == item.sha
    assert show_name.content is not None
    assert "show-wf" in show_name.content

    # Show by SHA
    show_sha = catalog_show_command(item.sha, cwd=fs.base_path)
    assert show_sha.ok
    assert show_sha.item is not None

    # Show missing
    show_missing = catalog_show_command("missing-item", cwd=fs.base_path)
    assert not show_missing.ok
    assert "not found" in show_missing.errors[0]


def test_catalog_delete_command(fs: FileSystem) -> None:
    item = create_catalog_item("task", "del-task", cwd=fs.base_path)

    del_res = catalog_delete_command(item.sha, cwd=fs.base_path)
    assert del_res.ok
    assert del_res.deleted

    del_missing = catalog_delete_command(item.sha, cwd=fs.base_path)
    assert not del_missing.ok
    assert not del_missing.deleted


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

    # wt catalog list --type workflow
    res_list_wf = runner.invoke(app, ["catalog", "list", "--type", "workflow"])
    assert res_list_wf.exit_code == 0
    assert "cli-wf" in res_list_wf.output

    # wt catalog show cli-wf
    res_show = runner.invoke(app, ["catalog", "show", "cli-wf"])
    assert res_show.exit_code == 0
    assert "Blueprint:" in res_show.output

    # wt catalog delete cli-wf --force
    res_del = runner.invoke(app, ["catalog", "delete", "cli-wf", "--force"])
    assert res_del.exit_code == 0
    assert "Deleted catalog blueprint" in res_del.output

    # wt catalog delete non-existent
    res_del_fail = runner.invoke(app, ["catalog", "delete", "non-existent", "--force"])
    assert res_del_fail.exit_code == 1
