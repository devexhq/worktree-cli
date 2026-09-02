"""Orchestration logic for ``wt catalog create`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogCreateCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType


def catalog_create_command(
    context: CliContext,
    item_type: CatalogItemType | str,
    name: str,
    output_format: str = "terminal",
) -> CatalogCreateCommandOutcome:
    """Create a new catalog blueprint under ``.worktree/catalog/<type>s/<name>.yml``.

    Args:
        context: CLI context instance.
        item_type: Blueprint type (workflow, task, step).
        name: Blueprint name.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogCreateCommandOutcome containing created record or errors.
    """
    result = Catalog(path=context.cwd, db=context.db.catalog).create(
        item_type=item_type,
        name=name,
    )
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogCreateCommandOutcome(
        result=result,
        item=result.item,
        errors=list(result.errors),
    )
