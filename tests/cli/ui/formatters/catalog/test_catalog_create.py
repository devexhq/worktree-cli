"""Tier 2 presentation contract tests for CatalogCreateFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.catalog.catalog_create import CatalogCreateFormatter
from worktree.core.catalog.models import CatalogCreateResult
from worktree.core.db import CatalogItemType, CatalogRecord

_RECORD = CatalogRecord(
    id=1,
    sha="workflow_1234567",
    item_type=CatalogItemType.WORKFLOW,
    name="test-workflow",
    path=Path("workflows/test-workflow.yml"),
    checksum="1234567890abcdef",
    created_at="2026-08-17T00:00:00Z",
    updated_at="2026-08-17T00:00:00Z",
)

CREATED_WORKFLOW = FormatterCase(
    data=CatalogCreateResult(item=_RECORD),
    view=CatalogCreateResult(item=_RECORD),
    render_expectations=[_RECORD.sha, _RECORD.item_type.value],
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
    render_expectations=[],
)

CATALOG_CREATE_CASES = [
    pytest.param(CREATED_WORKFLOW, id="created_workflow"),
    pytest.param(CREATION_ERROR, id="creation_error"),
]

CATALOG_CREATE_PAYLOAD_CASES = [
    pytest.param(
        CREATED_WORKFLOW,
        {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "item": {
                "id": 1,
                "sha": "workflow_1234567",
                "item_type": "workflow",
                "name": "test-workflow",
                "path": "workflows/test-workflow.yml",
                "checksum": "1234567890abcdef",
                "created_at": "2026-08-17T00:00:00Z",
                "updated_at": "2026-08-17T00:00:00Z",
            },
        },
        id="created_workflow",
    ),
    pytest.param(
        CREATION_ERROR,
        {
            "errors": ["Naming collision on blueprint."],
            "warnings": [],
            "fixes": ["Choose a different name"],
            "item": None,
        },
        id="creation_error",
    ),
]


class CatalogCreateFormatterTests:
    """Tier 2 presentation contract tests for CatalogCreateFormatter."""

    @pytest.mark.parametrize("case", CATALOG_CREATE_CASES)
    def test_transform_derives_expected_view(
        self, case: FormatterCase[CatalogCreateResult, CatalogCreateResult]
    ) -> None:
        """Verify transform derives the identity view representation."""
        assert CatalogCreateFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), CATALOG_CREATE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[CatalogCreateResult, CatalogCreateResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert CatalogCreateFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", CATALOG_CREATE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[CatalogCreateResult, CatalogCreateResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(CatalogCreateFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered
