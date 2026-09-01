"""Orchestration logic for ``wt catalog list`` CLI command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.common.utils import RichOutput
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogItemType

from ..models import CatalogListCommandOutcome
from ..renderers import (
    render_catalog_list,
    render_catalog_template_list,
)


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


def _render_scan_warnings(errors: list[str], *, output: RichOutput) -> None:
    for error in errors:
        output.add_error_panel("Catalog Scan Warning", error)


def catalog_list_command(
    context: CliContext,
    type_filter: CatalogItemType | str | None = None,
) -> CatalogListCommandOutcome:
    """List catalog blueprints with optional type filtering.

    Args:
        type_filter: Optional type filter (workflow, task, step).
        context: CLI context instance.

    Returns:
        CatalogListCommandOutcome containing listed records and errors.
    """
    output = context.output
    catalog = Catalog(path=context.cwd, db=context.db.catalog)

    if type_filter is not None and str(type_filter).lower() == "template":
        render_catalog_template_list(Catalog.list_packaged_templates(), output=output)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[])

    parsed_type, type_error = _parse_catalog_type_filter(type_filter)
    if type_error is not None:
        output.add_error_panel("Catalog Filter Error", type_error)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[type_error])

    scan_result = catalog.sync()
    if not scan_result.ok:
        _render_scan_warnings(scan_result.errors, output=output)

    items = catalog.list(kind=parsed_type)
    render_catalog_list(items, output=output)
    return CatalogListCommandOutcome(items=items, type_filter=parsed_type, errors=list(scan_result.errors))
