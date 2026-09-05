"""Tier 2 presentation contract tests for CatalogDeleteFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.catalog.catalog_delete import CatalogDeleteFormatter
from worktree.core.catalog.models import CatalogDeleteResult
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


class CatalogDeleteFormatterTests:
    """Tests for CatalogDeleteFormatter."""

    def test_to_rich_when_deleted_renders_sha_and_path(self) -> None:
        formatter = CatalogDeleteFormatter()
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

        rendered = render_rich(formatter.to_rich(result))
        assert item.sha in rendered
        assert str(item.path) in rendered

    def test_to_rich_when_cancelled_renders_cancellation_message(self) -> None:
        formatter = CatalogDeleteFormatter()
        result = CatalogDeleteResult(cancelled=True, errors=["Deletion cancelled."])

        rendered = render_rich(formatter.to_rich(result))
        assert "Deletion cancelled." in rendered

    def test_to_rich_when_errors_renders_error_message(self) -> None:
        formatter = CatalogDeleteFormatter()
        result = CatalogDeleteResult(errors=["Catalog blueprint 'not-found' not found."])

        rendered = render_rich(formatter.to_rich(result))
        assert "Catalog blueprint 'not-found' not found." in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = CatalogDeleteFormatter()
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

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
            "deleted": True,
            "cancelled": False,
        }
