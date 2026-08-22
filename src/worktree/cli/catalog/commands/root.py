"""Orchestration logic for ``wt catalog`` CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.fs import get_catalog_templates_dir
from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import (
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    get_catalog_dir,
    get_catalog_item,
    scan_and_index_catalog,
)
from worktree.core.db import CatalogItemType

from ..models import (
    CatalogCreateCommandOutcome,
    CatalogDeleteCommandOutcome,
    CatalogListCommandOutcome,
    CatalogShowCommandOutcome,
)
from ..renderers import (
    render_catalog_create_success,
    render_catalog_delete_success,
    render_catalog_list,
    render_catalog_show,
    render_catalog_template_list,
    render_template_show_content,
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


def _find_packaged_templates(sha_or_name: str) -> list[tuple[str, str]]:
    """Return (relative_path, content) pairs for packaged templates matching `sha_or_name`."""
    root = get_catalog_templates_dir()
    found: list[tuple[str, str]] = []
    for type_dir in ("workflows", "tasks", "steps"):
        candidate = (
            (root / type_dir / "default.yml")
            if sha_or_name == "default"
            else (root / type_dir / "wt" / f"{sha_or_name}.yml")
        )
        if candidate.is_file():
            rel_path = f"{type_dir}/default.yml" if sha_or_name == "default" else f"{type_dir}/wt/{sha_or_name}.yml"
            found.append((rel_path, candidate.read_text(encoding="utf-8")))
    return found


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

    if type_filter is not None and str(type_filter).lower() == "template":
        render_catalog_template_list(_packaged_template_defaults(), rich_output=output)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[])

    parsed_type, type_error = _parse_catalog_type_filter(type_filter)
    if type_error is not None:
        output.error_panel("Catalog Filter Error", type_error)
        return CatalogListCommandOutcome(items=[], type_filter=None, errors=[type_error])

    scan_result = scan_and_index_catalog(cwd=cwd)
    if not scan_result.ok:
        _render_scan_warnings(scan_result.errors, rich_output=output)

    items = [i for i in scan_result.items if parsed_type is None or i.item_type == parsed_type]
    render_catalog_list(items, rich_output=output)
    return CatalogListCommandOutcome(items=items, type_filter=parsed_type, errors=list(scan_result.errors))


def catalog_create_command(
    item_type: CatalogItemType | str,
    name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogCreateCommandOutcome:
    """Create a new catalog blueprint under ``.worktree/catalog/<type>s/<name>.yml``.

    Args:
        item_type: Blueprint type (workflow, task, step).
        name: Blueprint name.
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
            cwd=cwd,
        )
    except Exception as exc:
        error_message = str(exc)
        output.error_panel("Catalog Creation Failed", error_message)
        return CatalogCreateCommandOutcome(item=None, errors=[error_message])

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

    resolution_result = get_catalog_item(sha_or_name, cwd=cwd)
    item = resolution_result.resolved
    if not resolution_result.ok or item is None:
        found = _find_packaged_templates(sha_or_name)
        if found:
            for rel_path, content in found:
                render_template_show_content(rel_path, content, rich_output=output)
            return CatalogShowCommandOutcome(item=None, content=found[0][1])

        error_message = f"Catalog blueprint or template '{sha_or_name}' not found."
        output.error_panel("Catalog Show Failed", error_message)
        return CatalogShowCommandOutcome(item=None, content=None, errors=[error_message])

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_message = f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"
        output.error_panel("Catalog Show Failed", error_message)
        return CatalogShowCommandOutcome(item=item, content=None, errors=[error_message])

    render_catalog_show(item, content, rich_output=output)
    return CatalogShowCommandOutcome(item=item, content=content)


def catalog_delete_command(
    sha_or_name: str,
    force: bool = False,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> CatalogDeleteCommandOutcome:
    """Delete a catalog blueprint file and its database index record.

    Args:
        sha_or_name: SHA identifier or name of the blueprint to delete.
        force: When True, skip the confirmation prompt.
        cwd: Optional CWD path.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogDeleteCommandOutcome indicating deletion status.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not force:
        try:
            confirmed = typer.confirm(
                f"Are you sure you want to delete catalog blueprint '{sha_or_name}'?",
                default=False,
            )
        except typer.Abort:
            confirmed = False
        if not confirmed:
            output.info("Deletion cancelled.")
            return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=["Deletion cancelled."])

    deleted_item = delete_catalog_item_by_sha_or_name(sha_or_name, cwd=cwd)
    if deleted_item is None:
        error_message = f"Catalog blueprint '{sha_or_name}' not found."
        output.error_panel("Catalog Delete Failed", error_message)
        return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=[error_message])

    render_catalog_delete_success(deleted_item, rich_output=output)
    return CatalogDeleteCommandOutcome(item=deleted_item, deleted=True)
