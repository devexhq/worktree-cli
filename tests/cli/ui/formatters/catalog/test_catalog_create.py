"""Tier 2 presentation contract tests for CatalogCreateFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.harness.formatter import (
    FormatterCase,
    assert_json_payload_matches_published_shape,
    assert_rich_render_shows_every_view_value,
)
from worktree.cli.ui.formatters.catalog.catalog_create import CatalogCreateFormatter
from worktree.core.catalog.models import CatalogCreateResult
from worktree.core.db import CatalogItemType, CatalogRecord

_RECORD = CatalogRecord(
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

CREATED_BLUEPRINT = FormatterCase(
    data=CatalogCreateResult(item=_RECORD),
    view=CatalogCreateResult(item=_RECORD),
    render_expectations=[_RECORD.sha, _RECORD.item_type.value, ".worktree/catalog/blueprints/test-blueprint.yml"],
)

CREATION_ERROR = FormatterCase(
    data=CatalogCreateResult(
        item=None,
        errors=["Naming collision on blueprint."],
        fixes=["Choose a different name"],
    ),
    view=CatalogCreateResult(
        item=None,
        errors=["Naming collision on blueprint."],
        fixes=["Choose a different name"],
    ),
    render_expectations=["Naming collision on blueprint.", "Choose a different name"],
)

CATALOG_CREATE_CASES = [
    pytest.param(CREATED_BLUEPRINT, id="created_blueprint"),
    pytest.param(CREATION_ERROR, id="creation_error"),
]

CATALOG_CREATE_PAYLOAD_CASES = [
    pytest.param(
        CREATED_BLUEPRINT,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "error_code": None,
            "item": {
                "id": 1,
                "key": "test-blueprint",
                "sha": "blueprint_1234567",
                "item_type": "blueprint",
                "name": "test-blueprint",
                "namespace": None,
                "path": "blueprints/test-blueprint.yml",
                "checksum": "1234567890abcdef",
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        },
        id="created_blueprint",
    ),
    pytest.param(
        CREATION_ERROR,
        {
            "errors": ["Naming collision on blueprint."],
            "warnings": [],
            "fixes": ["Choose a different name"],
            "error_code": None,
            "item": None,
        },
        id="creation_error",
    ),
]


class CatalogCreateFormatterTests:
    """Tier 2 presentation contract tests for CatalogCreateFormatter."""

    @pytest.mark.parametrize(("case", "expected_payload"), CATALOG_CREATE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[CatalogCreateResult, CatalogCreateResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the published wire format dict."""
        assert_json_payload_matches_published_shape(CatalogCreateFormatter, case.data, expected_payload)

    @pytest.mark.parametrize("case", CATALOG_CREATE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[CatalogCreateResult, CatalogCreateResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        assert_rich_render_shows_every_view_value(CatalogCreateFormatter, case.data, case.render_expectations)
