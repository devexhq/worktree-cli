"""Orchestration logic for ``wt catalog`` CLI commands."""

from __future__ import annotations

from pathlib import Path

from getworktree.commands.catalog.models import (
    CatalogCreateCommandOutcome,
    CatalogDeleteCommandOutcome,
    CatalogListCommandOutcome,
    CatalogShowCommandOutcome,
)
from getworktree.commands.catalog.renderers import (
    render_catalog_create_success,
    render_catalog_delete_success,
    render_catalog_list,
    render_catalog_show,
)
from getworktree.common.utils import RichOutput
from getworktree.core.catalog.inventory import (
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    get_catalog_dir,
    get_catalog_item,
    scan_and_index_catalog,
)
from getworktree.core.db import CatalogItemType

_DEFAULT_RICH_OUTPUT = RichOutput()


def catalog_list_command(
    type_filter: CatalogItemType | str | None = None,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogListCommandOutcome:
    """List catalog blueprints with optional type filtering.

    Args:
        type_filter: Optional type filter (workflow, task, step).
        cwd: Optional CWD path.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogListCommandOutcome containing listed records and errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    parsed_type: CatalogItemType | None = None
    if type_filter is not None:
        if isinstance(type_filter, CatalogItemType):
            parsed_type = type_filter
        else:
            try:
                parsed_type = CatalogItemType(str(type_filter).lower())
            except ValueError:
                allowed = ", ".join([t.value for t in CatalogItemType])
                error_msg = f"Invalid --type argument '{type_filter}'. Allowed choices: {allowed}"
                output.error_panel("Catalog Filter Error", error_msg)
                return CatalogListCommandOutcome(
                    items=[],
                    type_filter=None,
                    errors=[error_msg],
                )

    scan_res = scan_and_index_catalog(cwd=cwd)
    if not scan_res.ok:
        for err in scan_res.errors:
            output.error_panel("Catalog Scan Warning", err)

    items = scan_res.items
    if parsed_type is not None:
        items = [i for i in items if i.item_type == parsed_type]

    render_catalog_list(items, rich_output=output)

    return CatalogListCommandOutcome(
        items=items,
        type_filter=parsed_type,
        errors=list(scan_res.errors),
    )


def catalog_create_command(
    item_type: CatalogItemType | str,
    name: str,
    template: str | None = None,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogCreateCommandOutcome:
    """Create a new catalog blueprint under ``.worktree/catalog/<type>s/<name>.yml``.

    Args:
        item_type: Blueprint type (workflow, task, step).
        name: Blueprint name.
        template: Optional built-in template name to instantiate from.
        cwd: Optional CWD path.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogCreateCommandOutcome containing created record or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    try:
        record = create_catalog_item(
            item_type=item_type,
            name=name,
            template_name=template,
            cwd=cwd,
        )
    except Exception as exc:
        error_msg = str(exc)
        output.error_panel("Catalog Creation Failed", error_msg)
        return CatalogCreateCommandOutcome(item=None, errors=[error_msg])

    render_catalog_create_success(record, rich_output=output)
    return CatalogCreateCommandOutcome(item=record)


def catalog_show_command(
    sha_or_name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogShowCommandOutcome:
    """Show details and definition content of a catalog blueprint.

    Args:
        sha_or_name: SHA identifier or name of the blueprint.
        cwd: Optional CWD path.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogShowCommandOutcome containing record and content or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    item = get_catalog_item(sha_or_name, cwd=cwd)
    if item is None:
        error_msg = f"Catalog blueprint '{sha_or_name}' not found."
        output.error_panel("Catalog Show Failed", error_msg)
        return CatalogShowCommandOutcome(item=None, content=None, errors=[error_msg])

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_msg = f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"
        output.error_panel("Catalog Show Failed", error_msg)
        return CatalogShowCommandOutcome(item=item, content=None, errors=[error_msg])

    render_catalog_show(item, content, rich_output=output)
    return CatalogShowCommandOutcome(item=item, content=content)


def catalog_delete_command(
    sha_or_name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogDeleteCommandOutcome:
    """Delete a catalog blueprint file and its database index record.

    Args:
        sha_or_name: SHA identifier or name of the blueprint to delete.
        cwd: Optional CWD path.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogDeleteCommandOutcome indicating deletion status.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    deleted_item = delete_catalog_item_by_sha_or_name(sha_or_name, cwd=cwd)
    if deleted_item is None:
        error_msg = f"Catalog blueprint '{sha_or_name}' not found."
        output.error_panel("Catalog Delete Failed", error_msg)
        return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=[error_msg])

    render_catalog_delete_success(deleted_item, rich_output=output)
    return CatalogDeleteCommandOutcome(item=deleted_item, deleted=True)
