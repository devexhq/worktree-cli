"""Orchestration for ``wt templates`` and ``wt template list`` commands."""

from __future__ import annotations

from getworktree.common.utils import RichOutput
from getworktree.core.templates.inventory import (
    get_builtin_template,
    list_builtin_templates,
)
from getworktree.core.templates.models import TemplateType

from .models import (
    TemplatesCommandOutcome,
    TemplateShowCommandOutcome,
)
from .renderers import (
    render_template_show,
    render_templates_list,
)

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


def template_show_command(
    name: str,
    type_filter: TemplateType | str | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TemplateShowCommandOutcome:
    """Show metadata and YAML content of a specific built-in template.

    Args:
        name: Template name to show.
        type_filter: Optional template type filter.
        rich_output: Optional RichOutput presenter.

    Returns:
        TemplateShowCommandOutcome containing the template item if found.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    tmpl = get_builtin_template(name, type_filter=type_filter)
    if tmpl is None:
        type_msg = f" of type '{type_filter}'" if type_filter else ""
        error_msg = f"Template '{name}'{type_msg} not found."
        output.error_panel("Template Show Failed", error_msg)
        return TemplateShowCommandOutcome(template=None, errors=[error_msg])

    render_template_show(tmpl, rich_output=output)
    return TemplateShowCommandOutcome(template=tmpl)
