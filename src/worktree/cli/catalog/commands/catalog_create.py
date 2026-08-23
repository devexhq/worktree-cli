"""Orchestration logic for ``wt catalog create`` CLI command."""

from __future__ import annotations

from worktree.cli.context import Context
from worktree.core.catalog.services.inventory import create_catalog_item
from worktree.core.db import CatalogItemType

from ..models import CatalogCreateCommandOutcome
from ..renderers import render_catalog_create_success


def catalog_create_command(
    item_type: CatalogItemType | str,
    name: str,
    *,
    context: Context,
) -> CatalogCreateCommandOutcome:
    """Create a new catalog blueprint under ``.worktree/catalog/<type>s/<name>.yml``.

    Args:
        item_type: Blueprint type (workflow, task, step).
        name: Blueprint name.
        context: CLI context instance.

    Returns:
        CatalogCreateCommandOutcome containing created record or errors.
    """
    output = context.output

    try:
        record = create_catalog_item(
            item_type=item_type,
            name=name,
            path=context.cwd,
            db=context.db.catalog,
        )
    except Exception as exc:
        error_message = str(exc)
        output.add_error_panel("Catalog Creation Failed", error_message)
        return CatalogCreateCommandOutcome(item=None, errors=[error_message])

    render_catalog_create_success(record, output=output)
    return CatalogCreateCommandOutcome(item=record)
