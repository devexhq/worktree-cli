"""Tier 2 presentation contract tests for CatalogCreateFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.catalog.catalog_create import CatalogCreateFormatter
from worktree.core.catalog.models import CatalogCreateResult
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


class CatalogCreateFormatterTests:
    """Tests for CatalogCreateFormatter."""

    def test_to_rich_when_created_renders_sha_and_type(self) -> None:
        formatter = CatalogCreateFormatter()
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        rendered = render_rich(formatter.to_rich(result))
        assert item.sha in rendered

    def test_to_rich_when_errors_renders_error_message(self) -> None:
        formatter = CatalogCreateFormatter()
        result = CatalogCreateResult(errors=["Naming collision on blueprint."])

        rendered = render_rich(formatter.to_rich(result))
        assert "Naming collision on blueprint." in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = CatalogCreateFormatter()
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        dumped = formatter.to_json_serializable(result)
        assert dumped == {
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
        }
