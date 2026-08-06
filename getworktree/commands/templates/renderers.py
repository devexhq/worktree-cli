"""Rich-facing formatters for ``wt templates`` output table."""

from __future__ import annotations

from rich.table import Table

from getworktree.common.utils import RichOutput
from getworktree.core.templates.models import BuiltinTemplate

_DEFAULT_RICH_OUTPUT = RichOutput()


def build_templates_table(templates: list[BuiltinTemplate]) -> Table:
    """Build the Rich table for displaying wt-defined built-in templates.

    Args:
        templates: List of BuiltinTemplate instances.

    Returns:
        A Rich Table with NAME, TYPE, DESCRIPTION, SUMMARY columns.
    """
    table = Table(title="wt-defined Templates:", show_header=True)
    table.add_column("NAME", no_wrap=True)
    table.add_column("TYPE", no_wrap=True)
    table.add_column("DESCRIPTION")
    table.add_column("SUMMARY")

    for tmpl in templates:
        table.add_row(
            tmpl.name,
            tmpl.type.value if hasattr(tmpl.type, "value") else str(tmpl.type),
            tmpl.description,
            tmpl.summary,
        )

    return table


def render_templates_list(
    templates: list[BuiltinTemplate],
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state or built-in templates table."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not templates:
        output.info("No built-in templates found.")
    else:
        output.info(build_templates_table(templates))
