"""ComponentFormatters for catalog CLI domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.cli.catalog.renderers import build_catalog_table, build_catalog_template_table
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.common.utils import enum_value
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
)
from worktree.core.db import CatalogRecord


def _render_list_errors(data: CatalogListResult) -> Panel | None:
    if data.errors:
        return Panel("\n".join(data.errors), title="Catalog Filter Error", border_style="red")
    return None


def _render_list_empty(data: CatalogListResult) -> Any:
    renderables: list[Any] = [Text("No catalog blueprints found.")]
    for warning in data.warnings:
        renderables.append(Panel(warning, title="Catalog Scan Warning", border_style="red"))
    return Group(*renderables) if data.warnings else renderables[0]


def _render_list_items(data: CatalogListResult) -> Any:
    table = build_catalog_table(data.items)
    if not data.warnings:
        return table
    renderables: list[Any] = [table]
    for warning in data.warnings:
        renderables.append(Panel(warning, title="Catalog Scan Warning", border_style="red"))
    return Group(*renderables)


class CatalogListFormatter(ComponentFormatter[CatalogListResult]):
    """Formatter for catalog list command results."""

    def to_rich(self, data: CatalogListResult) -> Any:
        """Render catalog blueprint list, templates table, or empty state.

        Args:
            data: Structured result of catalog list operation.

        Returns:
            Rich renderable object (Table, Group, Panel, or Text).
        """
        error_panel = _render_list_errors(data)
        if error_panel is not None:
            return error_panel

        if data.templates:
            return build_catalog_template_table(data.templates)

        if data.type_filter == "template":
            return Text("No packaged templates found.")

        if not data.items:
            return _render_list_empty(data)

        return _render_list_items(data)

    def to_json_serializable(self, data: CatalogListResult) -> dict[str, Any]:
        """Convert CatalogListResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of catalog list operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def _render_show_template_matches(matches: list[tuple[str, str]]) -> Any:
    renderables: list[Any] = []
    for rel_path, content in matches:
        renderables.append(Text.from_markup(f"[bold green]Template:[/]    {rel_path}"))
        renderables.append(Text.from_markup("\n[bold cyan]Definition:[/]\n"))
        if content:
            renderables.append(Syntax(content.strip(), "yaml"))
    return Group(*renderables) if len(renderables) > 1 else (renderables[0] if renderables else Text(""))


def _render_show_item(item: CatalogRecord, content: str | None) -> Group:
    t_type = enum_value(item.item_type)
    rel_path = Path(".worktree") / "catalog" / item.path
    renderables: list[Any] = [
        Text.from_markup(f"[bold green]Blueprint:[/]   {item.name} ({item.sha})"),
        Text.from_markup(f"[bold green]Type:[/]        {t_type}"),
        Text.from_markup(f"[bold green]Path:[/]        {rel_path}"),
        Text.from_markup(f"[bold green]Checksum:[/]    {item.checksum}"),
    ]
    if content:
        renderables.append(Text.from_markup("\n[bold cyan]Definition:[/]\n"))
        renderables.append(Syntax(content.strip(), "yaml"))
    return Group(*renderables)


class CatalogShowFormatter(ComponentFormatter[CatalogShowResult]):
    """Formatter for catalog show command results."""

    def to_rich(self, data: CatalogShowResult) -> Any:
        """Render blueprint header metadata and YAML syntax highlighting or template.

        Args:
            data: Structured result of catalog show operation.

        Returns:
            Rich renderable object (Group, Panel, or Text).
        """
        if data.errors or not data.ok:
            error_message = "\n\n".join(data.errors) if data.errors else "Catalog blueprint not found."
            if data.fixes:
                error_message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
            return Panel(error_message, title="Catalog Show Failed", border_style="red")

        if data.template_matches:
            return _render_show_template_matches(data.template_matches)

        if data.item is not None:
            return _render_show_item(data.item, data.content)

        return Text("")

    def to_json_serializable(self, data: CatalogShowResult) -> dict[str, Any]:
        """Convert CatalogShowResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of catalog show operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class CatalogDeleteFormatter(ComponentFormatter[CatalogDeleteResult]):
    """Formatter for catalog delete command results."""

    def to_rich(self, data: CatalogDeleteResult) -> Any:
        """Render single-line deletion confirmation, cancellation, or error panel.

        Args:
            data: Structured result of catalog delete operation.

        Returns:
            Rich renderable object (Text, Panel).
        """
        if data.cancelled:
            return Text("Deletion cancelled.")

        if data.errors or not data.ok:
            error_message = "\n\n".join(data.errors) if data.errors else "Catalog delete failed."
            if data.fixes:
                error_message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
            return Panel(error_message, title="Catalog Delete Failed", border_style="red")

        if data.deleted and data.item is not None:
            return Text(f"Deleted catalog blueprint '{data.item.sha}' ({data.item.path}).")

        return Text("")

    def to_json_serializable(self, data: CatalogDeleteResult) -> dict[str, Any]:
        """Convert CatalogDeleteResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of catalog delete operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class CatalogCreateFormatter(ComponentFormatter[CatalogCreateResult]):
    """Formatter for catalog create command results."""

    def to_rich(self, data: CatalogCreateResult) -> Any:
        """Render blueprint creation confirmation or failure panel.

        Args:
            data: Structured result of catalog create operation.

        Returns:
            Rich renderable object (Text, Panel).
        """
        if data.errors or not data.ok or data.item is None:
            error_message = "\n\n".join(data.errors) if data.errors else "Catalog creation failed."
            if data.fixes:
                error_message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
            return Panel(error_message, title="Catalog Creation Failed", border_style="red")

        t_type = enum_value(data.item.item_type)
        rel_path = Path(".worktree") / "catalog" / data.item.path
        return Text(f"Created catalog blueprint '{data.item.sha}' (type: {t_type}) at '{rel_path}'.")

    def to_json_serializable(self, data: CatalogCreateResult) -> dict[str, Any]:
        """Convert CatalogCreateResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of catalog create operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_catalog_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all catalog ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(CatalogListResult, CatalogListFormatter())
    target.register(CatalogShowResult, CatalogShowFormatter())
    target.register(CatalogDeleteResult, CatalogDeleteFormatter())
    target.register(CatalogCreateResult, CatalogCreateFormatter())


# Register default catalog formatters on the central ui_dispatcher
register_catalog_formatters()
