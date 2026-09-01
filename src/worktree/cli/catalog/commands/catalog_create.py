"""Orchestration logic for ``wt catalog create`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogCreateCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogCreateResult
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
    catalog = Catalog(path=context.cwd, db=context.db.catalog)

    try:
        record = catalog.create(
            item_type=item_type,
            name=name,
        )
    except Exception as exc:
        error_message = str(exc)
        result = CatalogCreateResult(errors=[error_message])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogCreateCommandOutcome(result=result, item=None, errors=[error_message])

    result = CatalogCreateResult(item=record)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogCreateCommandOutcome(result=result, item=record)
