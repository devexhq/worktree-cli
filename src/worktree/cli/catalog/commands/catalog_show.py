"""Orchestration logic for ``wt catalog show`` CLI command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.catalog import Catalog
from worktree.core.catalog.services.inventory import get_catalog_dir

from ..models import CatalogShowCommandOutcome
from ..renderers import (
    render_catalog_show,
    render_template_show_content,
)


def catalog_show_command(
    context: CliContext,
    sha_or_name: str,
) -> CatalogShowCommandOutcome:
    """Show details and definition content of a catalog blueprint.

    Args:
        sha_or_name: SHA identifier or name of the blueprint.
        context: CLI context instance.

    Returns:
        CatalogShowCommandOutcome containing record and content or errors.
    """
    output = context.output
    catalog = Catalog(path=context.cwd, db=context.db.catalog)

    resolution_result = catalog.get(sha_or_name)
    item = resolution_result.resolved
    if not resolution_result.ok or item is None:
        found = Catalog.find_packaged_templates(sha_or_name)
        if found:
            for rel_path, content in found:
                render_template_show_content(rel_path, content, output=output)
            return CatalogShowCommandOutcome(item=None, content=found[0][1])

        error_message = f"Catalog blueprint or template '{sha_or_name}' not found."
        output.add_error_panel("Catalog Show Failed", error_message)
        return CatalogShowCommandOutcome(item=None, content=None, errors=[error_message])

    catalog_dir = get_catalog_dir(context.cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_message = f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"
        output.add_error_panel("Catalog Show Failed", error_message)
        return CatalogShowCommandOutcome(item=item, content=None, errors=[error_message])

    render_catalog_show(item, content, output=output)
    return CatalogShowCommandOutcome(item=item, content=content)
