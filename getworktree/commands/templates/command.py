"""Orchestration for ``wt templates`` and ``wt template list`` commands."""

from __future__ import annotations

from getworktree.commands.templates.models import TemplatesCommandOutcome
from getworktree.commands.templates.renderers import render_templates_list
from getworktree.common.utils import RichOutput
from getworktree.core.templates.inventory import list_builtin_templates
from getworktree.core.templates.models import TemplateType

_DEFAULT_RICH_OUTPUT = RichOutput()


def templates_list_command(
    type_filter: TemplateType | str | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TemplatesCommandOutcome:
    """List wt-defined built-in templates with optional type filtering.

    Args:
        type_filter: Optional template type filter (workflow, task, step).
        rich_output: Optional RichOutput presenter.

    Returns:
        TemplatesCommandOutcome containing listed templates and status.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    result = list_builtin_templates(type_filter=type_filter)
    if not result.ok:
        for error in result.errors:
            output.error_panel("Template Listing Error", error)
        parsed_type = None
        if type_filter is not None and isinstance(type_filter, TemplateType):
            parsed_type = type_filter
        return TemplatesCommandOutcome(
            templates=[],
            type_filter=parsed_type,
            errors=list(result.errors),
        )

    render_templates_list(result.templates, rich_output=output)

    parsed_type = None
    if type_filter is not None:
        if isinstance(type_filter, TemplateType):
            parsed_type = type_filter
        else:
            try:
                parsed_type = TemplateType(str(type_filter).lower())
            except ValueError:
                pass

    return TemplatesCommandOutcome(
        templates=result.templates,
        type_filter=parsed_type,
    )
