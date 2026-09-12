"""Unit tests for catalog data models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from worktree.core.blueprint import BlueprintDefinition
from worktree.core.catalog.models import CatalogItem
from worktree.core.db import CatalogItemType


class CatalogItemTests:
    """Unit tests for catalog item identity derived from its path."""

    @pytest.mark.parametrize(
        ("path", "expected_type", "expected_key"),
        [
            pytest.param(
                Path("blueprints/wt/fix-tests.yml"),
                CatalogItemType.BLUEPRINT,
                "wt/fix-tests",
                id="nested_blueprint",
            ),
            pytest.param(
                Path("steps/lint.yaml"),
                CatalogItemType.STEP,
                "lint",
                id="root_step",
            ),
        ],
    )
    def test_derives_catalog_identity_from_valid_path(
        self,
        path: Path,
        expected_type: CatalogItemType,
        expected_key: str,
    ) -> None:
        item = CatalogItem(
            path=path,
            definition=BlueprintDefinition(name="Test blueprint"),
        )

        assert (item.item_type, item.key) == (expected_type, expected_key)

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(Path("/tmp/blueprints/test.yml"), id="absolute_path"),
            pytest.param(Path("blueprints/../test.yml"), id="parent_traversal"),
            pytest.param(Path("unknown/test.yml"), id="unknown_catalog_root"),
            pytest.param(Path("blueprints/test.json"), id="non_yaml_extension"),
            pytest.param(Path("blueprints"), id="missing_filename"),
        ],
    )
    def test_rejects_path_outside_catalog_document_roots(self, path: Path) -> None:
        with pytest.raises(ValidationError):
            CatalogItem(
                path=path,
                definition=BlueprintDefinition(name="Test blueprint"),
            )
