"""Orchestration logic for ``wt catalog show`` CLI command."""

from __future__ import annotations

from worktree.cli.context import Context
from worktree.common.fs import get_catalog_templates_dir
from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import (
    get_catalog_dir,
    get_catalog_item,
)

from ..models import CatalogShowCommandOutcome
from ..renderers import (
    render_catalog_show,
    render_template_show_content,
)

_DEFAULT_RICH_OUTPUT = RichOutput()


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


def catalog_show_command(
    sha_or_name: str,
    *,
    context: Context,
    rich_output: RichOutput | None = None,
) -> CatalogShowCommandOutcome:
    """Show details and definition content of a catalog blueprint.

    Args:
        sha_or_name: SHA identifier or name of the blueprint.
        context: CLI context instance.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogShowCommandOutcome containing record and content or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    resolution_result = get_catalog_item(sha_or_name, path=context.cwd, db=context.db.catalog)
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

    catalog_dir = get_catalog_dir(context.cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_message = f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"
        output.error_panel("Catalog Show Failed", error_message)
        return CatalogShowCommandOutcome(item=item, content=None, errors=[error_message])

    render_catalog_show(item, content, rich_output=output)
    return CatalogShowCommandOutcome(item=item, content=content)
