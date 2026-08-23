"""Orchestration logic for ``wt catalog create`` CLI command."""

from __future__ import annotations

from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import create_catalog_item
from worktree.core.config.models import CliContext
from worktree.core.db import CatalogItemType

from ..models import CatalogCreateCommandOutcome
from ..renderers import render_catalog_create_success

_DEFAULT_RICH_OUTPUT = RichOutput()


def catalog_create_command(
    item_type: CatalogItemType | str,
    name: str,
    *,
    cli_ctx: CliContext,
    rich_output: RichOutput | None = None,
) -> CatalogCreateCommandOutcome:
    """Create a new catalog blueprint under ``.worktree/catalog/<type>s/<name>.yml``.

    Args:
        item_type: Blueprint type (workflow, task, step).
        name: Blueprint name.
        cli_ctx: CLI context instance.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogCreateCommandOutcome containing created record or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    try:
        record = create_catalog_item(
            item_type=item_type,
            name=name,
            cwd=cli_ctx.cwd,
            db=cli_ctx.db,
        )
    except Exception as exc:
        error_message = str(exc)
        output.error_panel("Catalog Creation Failed", error_message)
        return CatalogCreateCommandOutcome(item=None, errors=[error_message])

    render_catalog_create_success(record, rich_output=output)
    return CatalogCreateCommandOutcome(item=record)
