"""Tier 2 presentation contract tests for CatalogListFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.catalog.catalog_list import CatalogListFormatter
from worktree.cli.ui.formatters.catalog.catalog_views import (
    CatalogItemView,
    CatalogListView,
    CatalogTemplateView,
)
from worktree.core.catalog.models import CatalogListResult
from worktree.core.db import CatalogItemType, CatalogRecord


def _sample_catalog_record() -> CatalogRecord:
    return CatalogRecord(
        id=1,
        sha="workflow_1234567",
        item_type=CatalogItemType.WORKFLOW,
        name="test-workflow",
        path=Path("workflows/test-workflow.yml"),
        checksum="1234567890abcdef",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
    )


WITH_ITEMS = FormatterCase(
    data=CatalogListResult(items=[_sample_catalog_record()]),
    view=CatalogListView(
        items=[
            CatalogItemView(
                id=1,
                sha="workflow_1234567",
                item_type="workflow",
                name="test-workflow",
                path="workflows/test-workflow.yml",
                checksum="1234567890abcdef",
                created_at="2026-08-17T00:00:00Z",
                updated_at="2026-08-17T00:00:00Z",
            )
        ],
        total_items=1,
    ),
    render_expectations=[
        _sample_catalog_record().name,
        _sample_catalog_record().sha,
        "workflow",
        "workflows/test-workflow.yml",
    ],
)


EMPTY_ITEMS = FormatterCase(
    data=CatalogListResult(items=[]),
    view=CatalogListView(
        items=[],
        total_items=0,
    ),
    render_expectations=[],
)


TEMPLATES = FormatterCase(
    data=CatalogListResult(templates=[("workflow", "workflows/default.yml")]),
    view=CatalogListView(
        templates=[CatalogTemplateView(item_type="workflow", path="workflows/default.yml")],
        total_items=0,
    ),
    render_expectations=[
        "workflow",
        "workflows/default.yml",
    ],
)


EMPTY_TEMPLATES = FormatterCase(
    data=CatalogListResult(type_filter="template", templates=[]),
    view=CatalogListView(
        type_filter="template",
        templates=[],
        total_items=0,
    ),
    render_expectations=[],
)


WITH_ERRORS = FormatterCase(
    data=CatalogListResult(errors=["Invalid --type argument 'invalid'."]),
    view=CatalogListView(
        errors=["Invalid --type argument 'invalid'."],
        total_items=0,
    ),
    render_expectations=[],
)


WITH_WARNINGS = FormatterCase(
    data=CatalogListResult(items=[_sample_catalog_record()], warnings=["Failed to parse corrupted.yml"]),
    view=CatalogListView(
        items=[
            CatalogItemView(
                id=1,
                sha="workflow_1234567",
                item_type="workflow",
                name="test-workflow",
                path="workflows/test-workflow.yml",
                checksum="1234567890abcdef",
                created_at="2026-08-17T00:00:00Z",
                updated_at="2026-08-17T00:00:00Z",
            )
        ],
        total_items=1,
        warnings=["Failed to parse corrupted.yml"],
    ),
    render_expectations=[
        _sample_catalog_record().name,
        _sample_catalog_record().sha,
        "workflow",
        "workflows/test-workflow.yml",
    ],
)


LIST_CASES = [
    pytest.param(WITH_ITEMS, id="with_items"),
    pytest.param(EMPTY_ITEMS, id="empty_items"),
    pytest.param(TEMPLATES, id="templates"),
    pytest.param(EMPTY_TEMPLATES, id="empty_templates"),
    pytest.param(WITH_ERRORS, id="with_errors"),
    pytest.param(WITH_WARNINGS, id="with_warnings"),
]


PAYLOAD_CASES = [
    pytest.param(
        WITH_ITEMS,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "items": [
                {
                    "id": 1,
                    "sha": "workflow_1234567",
                    "item_type": "workflow",
                    "name": "test-workflow",
                    "path": "workflows/test-workflow.yml",
                    "checksum": "1234567890abcdef",
                    "created_at": "2026-08-17T00:00:00Z",
                    "updated_at": "2026-08-17T00:00:00Z",
                }
            ],
            "type_filter": None,
            "templates": [],
            "total_items": 1,
        },
        id="with_items_payload",
    ),
    pytest.param(
        EMPTY_ITEMS,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "items": [],
            "type_filter": None,
            "templates": [],
            "total_items": 0,
        },
        id="empty_items_payload",
    ),
    pytest.param(
        TEMPLATES,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "items": [],
            "type_filter": None,
            "templates": [
                {
                    "item_type": "workflow",
                    "path": "workflows/default.yml",
                }
            ],
            "total_items": 0,
        },
        id="templates_payload",
    ),
    pytest.param(
        WITH_ERRORS,
        {
            "errors": ["Invalid --type argument 'invalid'."],
            "warnings": [],
            "fixes": [],
            "items": [],
            "type_filter": None,
            "templates": [],
            "total_items": 0,
        },
        id="with_errors_payload",
    ),
    pytest.param(
        WITH_WARNINGS,
        {
            "errors": [],
            "warnings": ["Failed to parse corrupted.yml"],
            "fixes": [],
            "items": [
                {
                    "id": 1,
                    "sha": "workflow_1234567",
                    "item_type": "workflow",
                    "name": "test-workflow",
                    "path": "workflows/test-workflow.yml",
                    "checksum": "1234567890abcdef",
                    "created_at": "2026-08-17T00:00:00Z",
                    "updated_at": "2026-08-17T00:00:00Z",
                }
            ],
            "type_filter": None,
            "templates": [],
            "total_items": 1,
        },
        id="with_warnings_payload",
    ),
]


class CatalogListFormatterTests:
    @pytest.mark.parametrize("case", LIST_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[CatalogListResult, CatalogListView]) -> None:
        assert CatalogListFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[CatalogListResult, CatalogListView],
        expected_payload: dict[str, Any],
    ) -> None:
        assert CatalogListFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", LIST_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[CatalogListResult, CatalogListView]) -> None:
        rendered = render_rich(CatalogListFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for warning in view.warnings:
            assert warning in rendered
