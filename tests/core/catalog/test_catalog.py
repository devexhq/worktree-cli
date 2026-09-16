"""Integration tests for catalog scaffolding, protection, discovery fallback, and collisions."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.common.filesystem import Filesystem
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogShowResult,
)
from worktree.core.catalog.services.inventory import compute_catalog_sha
from worktree.core.db import CatalogItemType, CatalogRecord

pytestmark = pytest.mark.integration


class CatalogTemplateScaffoldingTests:
    """Tests verifying scaffolding of blueprints and steps under correct type subdirectories."""

    @pytest.mark.parametrize(
        ("item_type", "name", "expected_rel_path"),
        [
            pytest.param(
                CatalogItemType.BLUEPRINT, "scaffold-task", Path("blueprints/scaffold-task.yml"), id="blueprint"
            ),
            pytest.param(CatalogItemType.STEP, "scaffold-step", Path("steps/scaffold-step.yml"), id="step"),
        ],
    )
    def test_catalog_create_scaffolds_yaml_template_under_correct_type_dir(
        self,
        isolated_workspace: Path,
        item_type: CatalogItemType,
        name: str,
        expected_rel_path: Path,
    ) -> None:
        """Create scaffolds YAML templates under .worktree/catalog/blueprints and steps."""
        catalog = Catalog(isolated_workspace)
        result = catalog.create(item_type, name)

        target_file = isolated_workspace / ".worktree" / "catalog" / expected_rel_path
        assert target_file.is_file()

        content = target_file.read_text(encoding="utf-8")
        expected_sha, expected_checksum = compute_catalog_sha(item_type, content)

        assert_model_equal(
            result,
            CatalogCreateResult(
                item=CatalogRecord.model_construct(
                    id=1,
                    key=name,
                    sha=expected_sha,
                    item_type=item_type,
                    name=name,
                    namespace=None,
                    path=expected_rel_path,
                    checksum=expected_checksum,
                    created_at=ANY_TIMESTAMP,
                    updated_at=ANY_TIMESTAMP,
                ),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )


class CatalogProtectionTests:
    """Tests verifying protection of bundled templates in the wt/ namespace."""

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("wt/starter-task", id="starter-task"),
            pytest.param("wt/fix-tests", id="fix-tests"),
        ],
    )
    def test_catalog_delete_rejects_deletion_of_bundled_packaged_templates(
        self, isolated_workspace: Path, template_name: str
    ) -> None:
        """catalog.delete rejects deleting templates in the wt/ namespace with ok=False."""
        catalog = Catalog(isolated_workspace)
        result = catalog.delete(template_name)

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


class CatalogDiscoveryFallbackTests:
    """Tests verifying fallback to bundled templates in package resources."""

    @pytest.mark.parametrize(
        "template_name",
        [
            pytest.param("fix-tests", id="bare-name"),
            pytest.param("wt/fix-tests", id="namespaced-name"),
        ],
    )
    def test_catalog_show_falls_back_to_bundled_template(self, isolated_workspace: Path, template_name: str) -> None:
        """catalog.show falls back to bundled templates via importlib.resources."""
        catalog = Catalog(isolated_workspace)
        result = catalog.show(template_name)

        expected_file = Filesystem().catalog_templates_dir / "blueprints" / "wt" / "fix-tests.yml"
        expected_content = expected_file.read_text(encoding="utf-8")

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


class CatalogCollisionTests:
    """Tests verifying collision detection during template creation."""

    @pytest.mark.parametrize(
        ("item_type", "name", "expected_rel_path"),
        [
            pytest.param(
                CatalogItemType.BLUEPRINT,
                "collision-task",
                Path("blueprints/collision-task.yml"),
                id="blueprint",
            ),
            pytest.param(
                CatalogItemType.STEP,
                "collision-step",
                Path("steps/collision-step.yml"),
                id="step",
            ),
        ],
    )
    def test_catalog_create_collision_returns_error(
        self,
        isolated_workspace: Path,
        item_type: CatalogItemType,
        name: str,
        expected_rel_path: Path,
    ) -> None:
        """catalog.create returns an error when target template already exists."""
        catalog = Catalog(isolated_workspace)
        result_first = catalog.create(item_type, name)
        assert result_first.item is not None

        target_file = isolated_workspace / ".worktree" / "catalog" / expected_rel_path
        assert target_file.is_file()

        result_second = catalog.create(item_type, name)
        assert_model_equal(
            result_second,
            CatalogCreateResult(
                item=None,
                errors=[f"Catalog blueprint collision at path '{expected_rel_path.as_posix()}'"],
                warnings=[],
                fixes=[],
            ),
        )
