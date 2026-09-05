"""Unit tests for catalog ComponentFormatters and UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.catalog import (
    CatalogCreateFormatter,
    CatalogDeleteFormatter,
    CatalogListFormatter,
    CatalogShowFormatter,
    register_catalog_formatters,
)
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
)
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

    def test_to_rich_with_items(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Table)
        rendered = render_rich(rich_renderable)
        assert "test-workflow" in rendered
        assert "workflow_1234567" in rendered

    def test_to_rich_empty(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(items=[])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert "No catalog blueprints found." in rich_renderable.plain

    def test_to_rich_templates(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(templates=[("workflow", "workflows/default.yml")])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Table)
        rendered = render_rich(rich_renderable)
        assert "Catalog Templates:" in rendered
        assert "workflows/default.yml" in rendered

    def test_to_rich_empty_templates(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(type_filter="template", templates=[])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert "No packaged templates found." in rich_renderable.plain

    def test_to_rich_with_errors(self) -> None:
        formatter = CatalogListFormatter()
        result = CatalogListResult(errors=["Invalid --type argument 'invalid'."])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Catalog Filter Error" in rendered
        assert "Invalid --type argument 'invalid'." in rendered

    def test_to_rich_with_warnings(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], warnings=["Failed to parse corrupted.yml"])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "test-workflow" in rendered
        assert "Catalog Scan Warning" in rendered
        assert "Failed to parse corrupted.yml" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = CatalogListFormatter()
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], type_filter=CatalogItemType.WORKFLOW)

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert len(dumped["items"]) == 1
        assert dumped["items"][0]["name"] == "test-workflow"
        assert dumped["type_filter"] == "workflow"
        assert dumped["errors"] == []


class CatalogShowFormatterTests:
    """Tests for CatalogShowFormatter."""

    def test_to_rich_blueprint_success(self) -> None:
        formatter = CatalogShowFormatter()
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test-workflow\nversion: 1\n")

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Blueprint:" in rendered
        assert "test-workflow" in rendered
        assert "Definition:" in rendered
        assert "name: test-workflow" in rendered

    def test_to_rich_template_matches(self) -> None:
        formatter = CatalogShowFormatter()
        result = CatalogShowResult(
            template_matches=[("workflows/default.yml", "name: default-workflow\n")],
            content="name: default-workflow\n",
        )

        rich_renderable = formatter.to_rich(result)
        assert rich_renderable is not None
        rendered = render_rich(rich_renderable)
        assert "Template:" in rendered
        assert "workflows/default.yml" in rendered
        assert "default-workflow" in rendered

    def test_to_rich_errors(self) -> None:
        formatter = CatalogShowFormatter()
        result = CatalogShowResult(errors=["Catalog blueprint 'missing' not found."])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Catalog Show Failed" in rendered
        assert "Catalog blueprint 'missing' not found." in rendered

    def test_to_json_serializable(self) -> None:
        formatter = CatalogShowFormatter()
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test\n")

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["item"]["name"] == "test-workflow"
        assert dumped["content"] == "name: test\n"
        assert dumped["errors"] == []


class CatalogDeleteFormatterTests:
    """Tests for CatalogDeleteFormatter."""

    def test_to_rich_deleted_success(self) -> None:
        formatter = CatalogDeleteFormatter()
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert f"Deleted catalog blueprint '{item.sha}' ({item.path})." in rich_renderable.plain

    def test_to_rich_cancelled(self) -> None:
        formatter = CatalogDeleteFormatter()
        result = CatalogDeleteResult(cancelled=True, errors=["Deletion cancelled."])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert "Deletion cancelled." in rich_renderable.plain

    def test_to_rich_errors(self) -> None:
        formatter = CatalogDeleteFormatter()
        result = CatalogDeleteResult(errors=["Catalog blueprint 'not-found' not found."])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Catalog Delete Failed" in rendered
        assert "Catalog blueprint 'not-found' not found." in rendered

    def test_to_json_serializable(self) -> None:
        formatter = CatalogDeleteFormatter()
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["deleted"] is True
        assert dumped["item"]["sha"] == item.sha


class CatalogCreateFormatterTests:
    """Tests for CatalogCreateFormatter."""

    def test_to_rich_created_success(self) -> None:
        formatter = CatalogCreateFormatter()
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert f"Created catalog blueprint '{item.sha}' (type: workflow)" in rich_renderable.plain

    def test_to_rich_errors(self) -> None:
        formatter = CatalogCreateFormatter()
        result = CatalogCreateResult(errors=["Naming collision on blueprint."])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Catalog Creation Failed" in rendered
        assert "Naming collision on blueprint." in rendered

    def test_to_json_serializable(self) -> None:
        formatter = CatalogCreateFormatter()
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["item"]["sha"] == item.sha
        assert dumped["errors"] == []


class CatalogDispatcherIntegrationTests:
    """Integration tests for UiDispatcher catalog formatters and JSON/terminal output."""

    def test_register_catalog_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)

        assert CatalogListResult in dispatcher._registry
        assert CatalogShowResult in dispatcher._registry
        assert CatalogDeleteResult in dispatcher._registry
        assert CatalogCreateResult in dispatcher._registry

    def test_ui_dispatcher_default_registrations(self) -> None:
        assert CatalogListResult in ui_dispatcher._registry
        assert CatalogShowResult in ui_dispatcher._registry
        assert CatalogDeleteResult in ui_dispatcher._registry
        assert CatalogCreateResult in ui_dispatcher._registry

    def test_dispatcher_list_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], type_filter="workflow")

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogListResult"
        assert len(payload["payload"]["items"]) == 1
        assert payload["payload"]["items"][0]["name"] == "test-workflow"

    def test_dispatcher_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test\n")

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogShowResult"
        assert payload["payload"]["item"]["sha"] == item.sha

    def test_dispatcher_delete_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogDeleteResult"
        assert payload["payload"]["deleted"] is True

    def test_dispatcher_create_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogCreateResult"
        assert payload["payload"]["item"]["name"] == "test-workflow"

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item])

        dispatcher.dispatch(result, output_format="terminal")

        out = buffer.getvalue()
        assert "test-workflow" in out
        assert "workflow_1234567" in out
