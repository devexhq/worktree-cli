from typing import Annotated

import typer

from getworktree.core.templates.models import TemplateType

from .command import template_show_command, templates_list_command

template_app = typer.Typer(
    name="template",
    help="Inspect built-in Worktree template definitions.",
    invoke_without_command=True,
)


@template_app.callback(invoke_without_command=True)
def template_callback(
    ctx: typer.Context,
    type: Annotated[
        TemplateType | None,
        typer.Option(
            "--type",
            help="Filter built-in templates by type (workflow, task, step).",
        ),
    ] = None,
):
    """Inspect built-in Worktree template definitions."""
    if ctx.invoked_subcommand is None:
        templates_list_command(type_filter=type.value if type is not None else None)


@template_app.command("list")
def template_list(
    ctx: typer.Context,
    type: Annotated[
        TemplateType | None,
        typer.Option(
            "--type",
            help="Filter built-in templates by type (workflow, task, step).",
        ),
    ] = None,
):
    """List wt-defined built-in templates."""
    templates_list_command(type_filter=type.value if type is not None else None)


@template_app.command("show")
def template_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Template name to show."),
    type: Annotated[
        TemplateType | None,
        typer.Option(
            "--type",
            help="Filter built-in templates by type (workflow, task, step).",
        ),
    ] = None,
):
    """Show metadata and definition content of a specific built-in template."""
    outcome = template_show_command(name, type_filter=type.value if type is not None else None)
    if not outcome.ok:
        raise typer.Exit(code=1)
