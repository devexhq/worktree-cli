"""Orchestration logic for ``wt catalog list`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogListCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def catalog_list_command(
    context: CliContext,
    type_filter: CatalogItemType | str | None = None,
    output_format: str = "terminal",
) -> CatalogListCommandOutcome:
    """List catalog blueprints with optional type filtering.

    Args:
        context: CLI context instance.
        type_filter: Optional type filter (workflow, task, step).
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogListCommandOutcome containing listed records and errors.
    """
    result = Catalog(path=context.cwd, db=context.db.catalog).list(type_filter=type_filter)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogListCommandOutcome(
        result=result,
        items=result.items,
        type_filter=result.type_filter,
        errors=list(result.errors),
    )
