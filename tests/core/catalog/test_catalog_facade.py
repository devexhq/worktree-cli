"""Tests for Catalog domain facade."""

from __future__ import annotations

from tests.helpers import FileSystem
from tests.types import AssertModel
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


class CatalogTests:
    def test_catalog_create(self, fs: FileSystem, assert_model: AssertModel) -> None:
        catalog = Catalog(fs.base_path)
        blueprint = catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")

        assert_model(
            blueprint,
            {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "item": {
                    "item_type": "blueprint",
                    "id": 1,
                    "namespace": None,
                    "key": "my-new-task",
                    "name": "my-new-task",
                },
            },
        )

    def test_catalog_get(self, fs: FileSystem, assert_model: AssertModel) -> None:
        catalog = Catalog(fs.base_path)
        catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")
        result = catalog.get("my-new-task")

        expected_blueprint = {
            "item_type": "blueprint",
            "id": 1,
            "namespace": None,
            "key": "my-new-task",
            "name": "my-new-task",
        }

        assert_model(
            result,
            {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "definition": None,
                "matches": [expected_blueprint],
                "requested_name": "my-new-task",
                "resolved": expected_blueprint,
                "status": "ok",
            },
        )

    def test_catalog_show(self, fs: FileSystem, assert_model: AssertModel) -> None:
        catalog = Catalog(fs.base_path)
        catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")
        result = catalog.show("my-new-task")
        assert_model(
            result,
            {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "item": {
                    "item_type": "blueprint",
                    "id": 1,
                    "namespace": None,
                    "key": "my-new-task",
                    "name": "my-new-task",
                },
                "content": "\n".join(
                    ['version: "1.0"', "name: my-new-task", "description: Custom blueprint", "steps: []", ""]
                ),
                "template_matches": [],
            },
        )

    def test_catalog_list(self, fs: FileSystem, assert_model: AssertModel) -> None:
        catalog = Catalog(fs.base_path)
        catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")
        result = catalog.list(kind=CatalogItemType.BLUEPRINT)

        assert_model(
            result,
            {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "items": [
                    {"item_type": "blueprint", "id": 1, "namespace": None, "key": "my-new-task", "name": "my-new-task"}
                ],
                "type_filter": "blueprint",
                "templates": [],
            },
        )

    def test_catalog_delete(self, fs: FileSystem, assert_model: AssertModel) -> None:
        catalog = Catalog(fs.base_path)
        catalog.create(CatalogItemType.BLUEPRINT, "my-new-task")
        result = catalog.delete("my-new-task")

        assert_model(
            result,
            {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "item": {
                    "item_type": "blueprint",
                    "id": 1,
                    "namespace": None,
                    "key": "my-new-task",
                    "name": "my-new-task",
                },
                "deleted": True,
                "cancelled": False,
            },
        )

        get_result = catalog.get("my-new-task")
        assert not get_result.ok

    def test_catalog_facade_templates_and_seed(self, fs: FileSystem) -> None:
        catalog = Catalog(fs.base_path)

        templates = Catalog.list_packaged_templates()
        assert len(templates) > 0

        defaults = Catalog.find_packaged_templates("default")
        assert len(defaults) > 0

        seed_res = catalog.seed()
        assert seed_res.ok

        sync_res = catalog.sync()
        assert sync_res.ok
