"""Tier 2 presentation contract tests for CatalogDeleteFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.catalog.catalog_delete import CatalogDeleteFormatter
from worktree.core.catalog.models import CatalogDeleteResult
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

DELETED = FormatterCase(
    data=CatalogDeleteResult(item=_RECORD, deleted=True, cancelled=False),
    view=CatalogDeleteResult(item=_RECORD, deleted=True, cancelled=False),
    render_expectations=[_RECORD.sha, str(_RECORD.path)],
)

CANCELLED = FormatterCase(
    data=CatalogDeleteResult(item=None, deleted=False, cancelled=True, errors=["Deletion cancelled."]),
    view=CatalogDeleteResult(item=None, deleted=False, cancelled=True, errors=["Deletion cancelled."]),
    render_expectations=[],
)

DELETE_ERROR = FormatterCase(
    data=CatalogDeleteResult(
        item=None,
        deleted=False,
        cancelled=False,
        errors=["Catalog blueprint 'missing' not found."],
        fixes=["Run `wt catalog list` to inspect available items"],
    ),
    view=CatalogDeleteResult(
        item=None,
        deleted=False,
        cancelled=False,
        errors=["Catalog blueprint 'missing' not found."],
        fixes=["Run `wt catalog list` to inspect available items"],
    ),
    render_expectations=[],
)

CATALOG_DELETE_CASES = [
    pytest.param(DELETED, id="deleted"),
    pytest.param(CANCELLED, id="cancelled"),
    pytest.param(DELETE_ERROR, id="delete_error"),
]

CATALOG_DELETE_PAYLOAD_CASES = [
    pytest.param(
        DELETED,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
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
            "deleted": True,
            "cancelled": False,
        },
        id="deleted",
    ),
    pytest.param(
        CANCELLED,
        {
            "errors": ["Deletion cancelled."],
            "warnings": [],
            "fixes": [],
            "item": None,
            "deleted": False,
            "cancelled": True,
        },
        id="cancelled",
    ),
    pytest.param(
        DELETE_ERROR,
        {
            "errors": ["Catalog blueprint 'missing' not found."],
            "warnings": [],
            "fixes": ["Run `wt catalog list` to inspect available items"],
            "item": None,
            "deleted": False,
            "cancelled": False,
        },
        id="delete_error",
    ),
]


class CatalogDeleteFormatterTests:
    """Tier 2 presentation contract tests for CatalogDeleteFormatter."""

    @pytest.mark.parametrize("case", CATALOG_DELETE_CASES)
    def test_transform_derives_expected_view(
        self, case: FormatterCase[CatalogDeleteResult, CatalogDeleteResult]
    ) -> None:
        assert CatalogDeleteFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), CATALOG_DELETE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[CatalogDeleteResult, CatalogDeleteResult],
        expected_payload: dict[str, Any],
    ) -> None:
        assert CatalogDeleteFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", CATALOG_DELETE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[CatalogDeleteResult, CatalogDeleteResult]
    ) -> None:
        rendered = render_rich(CatalogDeleteFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered
