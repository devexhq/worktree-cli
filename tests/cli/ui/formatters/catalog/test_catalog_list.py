"""Tier 2 presentation contract tests for CatalogListFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.catalog.catalog_list import CatalogListFormatter
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


class CatalogListFormatterTests:
    """Tests for CatalogListFormatter."""

    def test_to_rich_with_items_renders_name_and_sha(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item])

        rendered = render_rich(formatter.to_rich(result))
        assert "test-workflow" in rendered
        assert "workflow_1234567" in rendered

    def test_to_rich_when_empty_renders_no_items(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(items=[])

        rendered = render_rich(formatter.to_rich(result))
        assert "test-workflow" not in rendered

    def test_to_rich_templates_renders_template_path(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(templates=[("workflow", "workflows/default.yml")])

        rendered = render_rich(formatter.to_rich(result))
        assert "workflows/default.yml" in rendered

    def test_to_rich_empty_templates_renders_no_templates(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(type_filter="template", templates=[])

        rendered = render_rich(formatter.to_rich(result))
        assert "workflows/default.yml" not in rendered

    def test_to_rich_with_errors_renders_error_message(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(errors=["Invalid --type argument 'invalid'."])

        rendered = render_rich(formatter.to_rich(result))
        assert "Invalid --type argument 'invalid'." in rendered

    def test_to_rich_with_warnings_renders_warning_message(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], warnings=["Failed to parse corrupted.yml"])

        rendered = render_rich(formatter.to_rich(result))
        assert "test-workflow" in rendered
        assert "Failed to parse corrupted.yml" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], type_filter=CatalogItemType.WORKFLOW)

        dumped = formatter.to_json_serializable(result)
        assert dumped == {
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
            "type_filter": "workflow",
            "templates": [],
        }
