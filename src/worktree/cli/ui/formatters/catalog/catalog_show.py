"""ComponentFormatter for CatalogShowResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.common.utils import enum_value
from worktree.core.catalog.models import CatalogShowResult
from worktree.core.db import CatalogRecord


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
        """Render blueprint header metadata and YAML syntax highlighting or template."""
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
        """Convert CatalogShowResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
