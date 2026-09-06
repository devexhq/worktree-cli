"""ComponentFormatter for CatalogShowResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text

from worktree.cli.ui.formatters.catalog.catalog_views import (
    CatalogItemView,
    CatalogShowView,
    CatalogTemplateView,
)
from worktree.cli.ui.formatters.common import build_error_panel
from worktree.common.types import ComponentFormatter
from worktree.common.utils import enum_value
from worktree.core.catalog.models import CatalogShowResult


def _render_show_template_matches(matches: list[CatalogTemplateView], content: str | None) -> Any:
    renderables: list[Any] = []
    for template in matches:
        renderables.append(Text.from_markup(f"[bold green]Template:[/]    {template.path}"))
        if content:
            renderables.append(Text.from_markup("\n[bold cyan]Definition:[/]\n"))
            renderables.append(Syntax(content.strip(), "yaml"))
    return Group(*renderables) if len(renderables) > 1 else (renderables[0] if renderables else Text(""))


def _render_show_item(item: CatalogItemView, content: str | None, catalog_path_relative: str | None) -> Group:
    rel_path = catalog_path_relative or item.path
    renderables: list[Any] = [
        Text.from_markup(f"[bold green]Blueprint:[/]   {item.name} ({item.sha})"),
        Text.from_markup(f"[bold green]Type:[/]        {item.item_type}"),
        Text.from_markup(f"[bold green]Path:[/]        {rel_path}"),
        Text.from_markup(f"[bold green]Checksum:[/]    {item.checksum}"),
    ]
    if content:
        renderables.append(Text.from_markup("\n[bold cyan]Definition:[/]\n"))
        renderables.append(Syntax(content.strip(), "yaml"))
    return Group(*renderables)


class CatalogShowFormatter(ComponentFormatter[CatalogShowResult, CatalogShowView]):
    """Formatter for catalog show command results."""

    def transform(self, data: CatalogShowResult) -> CatalogShowView:
        """Derive the presentation-ready view from CatalogShowResult.

        Args:
            data: Domain CatalogShowResult.

        Returns:
            CatalogShowView with view models and derived paths.
        """
        item_view = None
        catalog_path_relative = None
        if data.item is not None:
            item_view = CatalogItemView(
                id=data.item.id,
                sha=data.item.sha,
                item_type=enum_value(data.item.item_type),
                name=data.item.name,
                path=data.item.path.as_posix(),
                checksum=data.item.checksum,
                created_at=data.item.created_at,
                updated_at=data.item.updated_at,
            )
            catalog_path_relative = (Path(".worktree") / "catalog" / data.item.path).as_posix()

        template_matches = [
            CatalogTemplateView(item_type="template", path=template_path) for template_path, _ in data.template_matches
        ]

        return CatalogShowView(
            item=item_view,
            content=data.content,
            template_matches=template_matches,
            catalog_path_relative=catalog_path_relative,
            errors=data.errors,
            warnings=data.warnings,
            fixes=data.fixes,
        )

    def to_rich(self, data: CatalogShowResult) -> Any:
        """Render blueprint header metadata and YAML syntax highlighting or template."""
        view = self.transform(data)

        if view.errors or (view.item is None and view.content is None and not view.template_matches):
            return build_error_panel(
                "Catalog Show Failed",
                view.errors,
                "Catalog blueprint not found.",
                view.fixes,
            )

        if view.template_matches:
            return _render_show_template_matches(view.template_matches, view.content)

        if view.item is not None:
            return _render_show_item(view.item, view.content, view.catalog_path_relative)

        return Text("")
