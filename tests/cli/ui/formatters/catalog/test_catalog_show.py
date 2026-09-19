"""Tier 2 presentation contract tests for CatalogShowFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.harness.formatter import (
    FormatterCase,
    assert_json_payload_matches_published_shape,
    assert_rich_render_shows_every_view_value,
    assert_transform_derives_expected_view,
)
from worktree.cli.ui.formatters.catalog.catalog_show import CatalogShowFormatter
from worktree.cli.ui.formatters.catalog.catalog_views import (
    CatalogItemView,
    CatalogShowView,
    CatalogTemplateView,
)
from worktree.core.catalog.models import CatalogShowResult
from worktree.core.db import CatalogItemType, CatalogRecord


def _sample_catalog_record() -> CatalogRecord:
    return CatalogRecord(
        id=1,
        key="test-blueprint",
        sha="blueprint_1234567",
        item_type=CatalogItemType.BLUEPRINT,
        name="test-blueprint",
        namespace=None,
        path=Path("blueprints/test-blueprint.yml"),
        checksum="1234567890abcdef",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
    )


BLUEPRINT_FOUND = FormatterCase(
    data=CatalogShowResult(item=_sample_catalog_record(), content="name: test-blueprint\nversion: 1\n"),
    view=CatalogShowView(
        item=CatalogItemView(
            id=1,
            sha="blueprint_1234567",
            item_type="blueprint",
            name="test-blueprint",
            path="blueprints/test-blueprint.yml",
            checksum="1234567890abcdef",
            created_at="2026-08-17T00:00:00Z",
            updated_at="2026-08-17T00:00:00Z",
        ),
        content="name: test-blueprint\nversion: 1\n",
        template_matches=[],
        catalog_path_relative=".worktree/catalog/blueprints/test-blueprint.yml",
        errors=[],
        warnings=[],
        fixes=[],
    ),
    render_expectations=[
        "test-blueprint",
        "blueprint_1234567",
        "blueprint",
        "1234567890abcdef",
        ".worktree/catalog/blueprints/test-blueprint.yml",
        "name: test-blueprint",
        "version: 1",
    ],
)

TEMPLATE_MATCH = FormatterCase(
    data=CatalogShowResult(
        template_matches=[("blueprints/default.yml", "name: default-blueprint\n")],
        content="name: default-blueprint\n",
    ),
    view=CatalogShowView(
        item=None,
        content="name: default-blueprint\n",
        template_matches=[CatalogTemplateView(item_type="template", path="blueprints/default.yml")],
        catalog_path_relative=None,
        errors=[],
        warnings=[],
        fixes=[],
    ),
    render_expectations=["blueprints/default.yml", "name: default-blueprint"],
)

ERRORS = FormatterCase(
    data=CatalogShowResult(errors=["Catalog blueprint 'missing' not found."]),
    view=CatalogShowView(
        item=None,
        content=None,
        template_matches=[],
        catalog_path_relative=None,
        errors=["Catalog blueprint 'missing' not found."],
        warnings=[],
        fixes=[],
    ),
    render_expectations=["Catalog blueprint 'missing' not found."],
)

SHOW_CASES = [
    pytest.param(BLUEPRINT_FOUND, id="blueprint_found"),
    pytest.param(TEMPLATE_MATCH, id="template_match"),
    pytest.param(ERRORS, id="errors"),
]

PAYLOAD_CASES = [
    pytest.param(
        BLUEPRINT_FOUND,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "item": {
                "id": 1,
                "sha": "blueprint_1234567",
                "item_type": "blueprint",
                "name": "test-blueprint",
                "path": "blueprints/test-blueprint.yml",
                "checksum": "1234567890abcdef",
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
            "content": "name: test-blueprint\nversion: 1\n",
            "template_matches": [],
            "catalog_path_relative": ".worktree/catalog/blueprints/test-blueprint.yml",
        },
        id="blueprint_found_payload",
    ),
    pytest.param(
        ERRORS,
        {
            "errors": ["Catalog blueprint 'missing' not found."],
            "warnings": [],
            "fixes": [],
            "item": None,
            "content": None,
            "template_matches": [],
            "catalog_path_relative": None,
        },
        id="errors_payload",
    ),
    pytest.param(
        TEMPLATE_MATCH,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "item": None,
            "content": "name: default-blueprint\n",
            "template_matches": [{"item_type": "template", "path": "blueprints/default.yml"}],
            "catalog_path_relative": None,
        },
        id="template_match_payload",
    ),
]


class CatalogShowFormatterTests:
    """Tier 2 presentation contract tests for CatalogShowFormatter."""

    @pytest.mark.parametrize("case", SHOW_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[CatalogShowResult, CatalogShowView]) -> None:
        """Verify transform derives the expected CatalogShowView."""
        assert_transform_derives_expected_view(CatalogShowFormatter, case.data, case.view)

    @pytest.mark.parametrize(("case", "expected_payload"), PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[CatalogShowResult, CatalogShowView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the published wire format dict."""
        assert_json_payload_matches_published_shape(CatalogShowFormatter, case.data, expected_payload)

    @pytest.mark.parametrize("case", SHOW_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[CatalogShowResult, CatalogShowView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        assert_rich_render_shows_every_view_value(CatalogShowFormatter, case.data, case.render_expectations)
