"""Orchestration logic for ``wt catalog show`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogShowCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogShowResult
from worktree.core.catalog.services.inventory import get_catalog_dir


def catalog_show_command(
    context: CliContext,
    sha_or_name: str,
    output_format: str = "terminal",
) -> CatalogShowCommandOutcome:
    """Show details and definition content of a catalog blueprint.

    Args:
        context: CLI context instance.
        sha_or_name: SHA identifier or name of the blueprint.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogShowCommandOutcome containing record and content or errors.
    """
    catalog = Catalog(path=context.cwd, db=context.db.catalog)

    resolution_result = catalog.get(sha_or_name)
    item = resolution_result.resolved
    if not resolution_result.ok or item is None:
        found = Catalog.find_packaged_templates(sha_or_name)
        if found:
            result = CatalogShowResult(template_matches=found, content=found[0][1] if found else None)
            ui_dispatcher.dispatch(result, output_format=output_format)
            return CatalogShowCommandOutcome(result=result, item=None, content=found[0][1])

        error_message = f"Catalog blueprint or template '{sha_or_name}' not found."
        result = CatalogShowResult(errors=[error_message])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogShowCommandOutcome(result=result, item=None, content=None, errors=[error_message])

    catalog_dir = get_catalog_dir(context.cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_message = f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"
        result = CatalogShowResult(item=item, errors=[error_message])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogShowCommandOutcome(result=result, item=item, content=None, errors=[error_message])

    result = CatalogShowResult(item=item, content=content)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogShowCommandOutcome(result=result, item=item, content=content)
