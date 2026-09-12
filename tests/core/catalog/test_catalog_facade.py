"""Tests for Catalog domain facade."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def test_catalog_facade_create_get_delete(fs: FileSystem) -> None:
    catalog = Catalog(fs.base_path)

    create_res = catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")
    assert create_res.ok
    assert create_res.item is not None
    assert create_res.item.name == "my-new-task"
    assert create_res.item.item_type == CatalogItemType.BLUEPRINT
    assert create_res.item.key == "my-new-task"

    res = catalog.get("my-new-task")
    assert res.ok
    assert res.resolved is not None
    assert res.resolved.name == "my-new-task"
    assert res.resolved.key == "my-new-task"

    show_res = catalog.show("my-new-task")
    assert show_res.ok
    assert show_res.item is not None
    assert show_res.item.name == "my-new-task"
    assert show_res.content is not None

    list_res = catalog.list(kind=CatalogItemType.BLUEPRINT)
    assert list_res.ok
    assert any(i.name == "my-new-task" for i in list_res.items)

    del_res = catalog.delete("my-new-task")
    assert del_res.ok
    assert del_res.deleted
    assert del_res.item is not None
    assert del_res.item.name == "my-new-task"

    res_after = catalog.get("my-new-task")
    assert not res_after.ok


def test_catalog_facade_templates_and_seed(fs: FileSystem) -> None:
    catalog = Catalog(fs.base_path)

    templates = Catalog.list_packaged_templates()
    assert len(templates) > 0

    defaults = Catalog.find_packaged_templates("default")
    assert len(defaults) > 0

    seed_res = catalog.seed()
    assert seed_res.ok

    sync_res = catalog.sync()
    assert sync_res.ok
