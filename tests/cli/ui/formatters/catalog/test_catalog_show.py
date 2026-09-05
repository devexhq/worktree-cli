"""Tier 2 presentation contract tests for CatalogShowFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.catalog.catalog_show import CatalogShowFormatter
from worktree.core.catalog.models import CatalogShowResult
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


class CatalogShowFormatterTests:
    """Tests for CatalogShowFormatter."""

    def test_to_rich_when_blueprint_found_renders_content(self) -> None:
        formatter = CatalogShowFormatter()
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test-workflow\nversion: 1\n")

        rendered = render_rich(formatter.to_rich(result))
        assert item.name in rendered
        assert item.sha in rendered
        assert "version: 1" in rendered

    def test_to_rich_when_template_matches_renders_template_path(self) -> None:
        formatter = CatalogShowFormatter()
        result = CatalogShowResult(
            template_matches=[("workflows/default.yml", "name: default-workflow\n")],
            content="name: default-workflow\n",
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "workflows/default.yml" in rendered
        assert "default-workflow" in rendered

    def test_to_rich_when_errors_renders_error_message(self) -> None:
        formatter = CatalogShowFormatter()
        result = CatalogShowResult(errors=["Catalog blueprint 'missing' not found."])

        rendered = render_rich(formatter.to_rich(result))
        assert "Catalog blueprint 'missing' not found." in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = CatalogShowFormatter()
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test\n")

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
            "content": "name: test\n",
            "template_matches": [],
        }
