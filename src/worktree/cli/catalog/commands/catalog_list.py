"""Orchestration logic for ``wt catalog list`` CLI command."""

from __future__ import annotations

from worktree.common.fs import get_catalog_templates_dir
from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.config.models import CliContext
from worktree.core.db import CatalogItemType

from ..models import CatalogListCommandOutcome
from ..renderers import (
    render_catalog_list,
    render_catalog_template_list,
)

_DEFAULT_RICH_OUTPUT = RichOutput()


def _packaged_template_defaults() -> list[tuple[str, str]]:
    """Return (type, relative_path) pairs for the three packaged `default.yml` templates."""
    root = get_catalog_templates_dir()
    rows: list[tuple[str, str]] = []
    for item_type in (CatalogItemType.WORKFLOW, CatalogItemType.TASK, CatalogItemType.STEP):
        rel_path = f"{item_type.value}s/default.yml"
        if (root / rel_path).is_file():
            rows.append((item_type.value, rel_path))
    return rows


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


def _render_scan_warnings(errors: list[str], *, rich_output: RichOutput) -> None:
    for error in errors:
        rich_output.error_panel("Catalog Scan Warning", error)


def catalog_list_command(
    type_filter: CatalogItemType | str | None = None,
    *,
    cli_ctx: CliContext,
    rich_output: RichOutput | None = None,
) -> CatalogListCommandOutcome:
    """List catalog blueprints with optional type filtering.

    Args:
        type_filter: Optional type filter (workflow, task, step).
        cli_ctx: CLI context instance.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogListCommandOutcome containing listed records and errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if type_filter is not None and str(type_filter).lower() == "template":
        render_catalog_template_list(_packaged_template_defaults(), rich_output=output)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[])

    parsed_type, type_error = _parse_catalog_type_filter(type_filter)
    if type_error is not None:
        output.error_panel("Catalog Filter Error", type_error)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[type_error])

    scan_result = scan_and_index_catalog(cwd=cli_ctx.cwd, db=cli_ctx.db)
    if not scan_result.ok:
        _render_scan_warnings(scan_result.errors, rich_output=output)

    items = [i for i in scan_result.items if parsed_type is None or i.item_type == parsed_type]
    render_catalog_list(items, rich_output=output)
    return CatalogListCommandOutcome(items=items, type_filter=parsed_type, errors=list(scan_result.errors))
