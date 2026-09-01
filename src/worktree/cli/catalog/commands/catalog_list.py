"""Orchestration logic for ``wt catalog list`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogListCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogListResult
from worktree.core.db import CatalogItemType


def _parse_catalog_type_filter(
    type_filter: CatalogItemType | str | None,
) -> tuple[CatalogItemType | None, str | None]:
    """Return (parsed_type, error_message). error_message is set on invalid filter strings."""
    if type_filter is None:
        return None, None
    if isinstance(type_filter, CatalogItemType):
        return type_filter, None
    try:
        return CatalogItemType(str(type_filter).lower()), None
    except ValueError:
        allowed = ", ".join([t.value for t in CatalogItemType])
        return None, f"Invalid --type argument '{type_filter}'. Allowed choices: {allowed}"


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
    catalog = Catalog(path=context.cwd, db=context.db.catalog)

    if type_filter is not None and str(type_filter).lower() == "template":
        templates = Catalog.list_packaged_templates()
        result = CatalogListResult(templates=templates, type_filter="template")
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogListCommandOutcome(result=result, items=[], type_filter=None, errors=[])

    parsed_type, type_error = _parse_catalog_type_filter(type_filter)
    if type_error is not None:
        result = CatalogListResult(errors=[type_error])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogListCommandOutcome(result=result, items=[], type_filter=None, errors=[type_error])

    scan_result = catalog.sync()
    items = catalog.list(kind=parsed_type)
    result = CatalogListResult(
        items=items,
        type_filter=parsed_type,
        warnings=list(scan_result.errors),
    )
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogListCommandOutcome(
        result=result,
        items=items,
        type_filter=parsed_type,
        errors=list(scan_result.errors),
    )
