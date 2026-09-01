"""Tests for Catalog domain facade."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def test_catalog_facade_create_get_delete(fs: FileSystem):
    catalog = Catalog(fs.base_path)

    # create
    record = catalog.create(CatalogItemType.TASK, "my-new-task")
    assert record.name == "my-new-task"
    assert record.item_type == CatalogItemType.TASK

    # get
    res = catalog.get("my-new-task")
    assert res.ok
    assert res.resolved is not None
    assert res.resolved.name == "my-new-task"

    # list
    items = catalog.list(kind=CatalogItemType.TASK)
    assert any(i.name == "my-new-task" for i in items)

    # delete
    deleted = catalog.delete("my-new-task")
    assert deleted is not None
    assert deleted.name == "my-new-task"

    # get after delete
    res_after = catalog.get("my-new-task")
    assert not res_after.ok


def test_catalog_facade_templates_and_seed(fs: FileSystem):
    catalog = Catalog(fs.base_path)

    templates = Catalog.list_packaged_templates()
    assert len(templates) > 0

    defaults = Catalog.find_packaged_templates("default")
    assert len(defaults) > 0

    seed_res = catalog.seed()
    assert seed_res.ok

    sync_res = catalog.sync()
    assert sync_res.ok
