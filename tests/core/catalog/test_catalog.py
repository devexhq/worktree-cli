"""Integration tests for catalog scaffolding, protection, discovery fallback, and collisions."""

from __future__ import annotations

from pathlib import Path

import pytest

from worktree.common.filesystem import Filesystem
from worktree.common.models import DefinitionResolutionStatus
from worktree.core.catalog import Catalog
from worktree.core.catalog.services.inventory import compute_catalog_sha
from worktree.core.db import CatalogItemType


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

        assert result.item is not None
        assert result.item.id == 1
        assert result.item.key == name
        assert result.item.sha == expected_sha
        assert result.item.item_type == item_type
        assert result.item.name == name
        assert result.item.namespace is None
        assert result.item.path == expected_rel_path
        assert result.item.checksum == expected_checksum
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []


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

        assert result.item is None
        assert result.deleted is False
        assert result.cancelled is False
        assert result.errors == [f"Cannot delete bundled catalog template '{template_name}'."]
        assert result.warnings == []
        assert result.fixes == []


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

        assert result.item is None
        assert result.content == expected_content
        assert result.template_matches == [("blueprints/wt/fix-tests.yml", expected_content)]
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []


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
        assert result_second.item is None
        assert result_second.errors == [f"Catalog blueprint collision at path '{expected_rel_path.as_posix()}'"]
        assert result_second.warnings == []
        assert result_second.fixes == []


class CatalogNamespaceSplittingTests:
    """Tests verifying namespaced identifiers split on the literal '/' boundary, not by character set."""

    def test_name_sharing_trailing_characters_with_namespace_resolves(self, isolated_workspace: Path) -> None:
        """catalog.get resolves 'wt/run-test', whose name ends in characters ('t') also present in its 'wt' namespace."""
        catalog = Catalog(isolated_workspace)
        catalog.save(
            "wt/run-test",
            {"name": "run-test", "description": "Regression fixture", "action": "run"},
            item_type=CatalogItemType.STEP,
        )

        result = catalog.get("wt/run-test", item_type=CatalogItemType.STEP)

        assert result.status == DefinitionResolutionStatus.OK
        assert result.resolved is not None
        assert result.resolved.name == "run-test"
        assert result.resolved.namespace == "wt"
