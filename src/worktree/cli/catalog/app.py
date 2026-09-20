from typing import Annotated

import typer

from worktree.cli.context import CliContext
from worktree.core.catalog.models import CatalogValidateStatus
from worktree.core.db import CatalogItemType

from .commands.catalog_create import catalog_create_command
from .commands.catalog_delete import catalog_delete_command
from .commands.catalog_list import catalog_list_command
from .commands.catalog_show import catalog_show_command
from .commands.catalog_validate import catalog_validate_command

catalog_app = typer.Typer(
    name="catalog",
    help="Inspect, index, and manage executable blueprints in .worktree/catalog/.",
    invoke_without_command=True,
)


@catalog_app.callback(invoke_without_command=True)
def catalog_callback(
    ctx: typer.Context,
    type: str | None = typer.Option(
        None,
        "--type",
        help="Filter catalog items by type (blueprint, step).",
    ),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Inspect and manage executable blueprints in .worktree/catalog/."""
    if ctx.invoked_subcommand is None:
        context: CliContext = ctx.obj["context"]
        result = catalog_list_command(context, type_filter=type, output_format=format)
        if not result.ok:
            raise typer.Exit(code=1)


@catalog_app.command("list")
def catalog_list(
    ctx: typer.Context,
    type: str | None = typer.Option(
        None,
        "--type",
        help="Filter catalog items by type (blueprint, step).",
    ),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """List catalog blueprints."""
    context: CliContext = ctx.obj["context"]
    result = catalog_list_command(context, type_filter=type, output_format=format)
    if not result.ok:
        raise typer.Exit(code=1)


@catalog_app.command("create")
def catalog_create(
    ctx: typer.Context,
    type: str = typer.Argument(..., help="Item type (blueprint, step)."),
    name: str = typer.Option(..., "--name", help="Name for the catalog blueprint file."),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Create a new catalog blueprint under .worktree/catalog/<type>s/<name>.yml."""
    context: CliContext = ctx.obj["context"]
    result = catalog_create_command(context, type, name, output_format=format)
    if not result.ok:
        raise typer.Exit(code=1)


@catalog_app.command("show")
def catalog_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Catalog blueprint SHA or name to show."),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Show metadata and definition content of a catalog blueprint."""
    context: CliContext = ctx.obj["context"]
    result = catalog_show_command(context, name, output_format=format)
    if not result.ok:
        raise typer.Exit(code=1)


@catalog_app.command("delete")
def catalog_delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Catalog blueprint SHA or name to delete."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip deletion confirmation prompt.",
    ),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Delete a catalog blueprint file and its database index record."""
    context: CliContext = ctx.obj["context"]
    result = catalog_delete_command(context, name, force=force, output_format=format)
    if not result.ok:
        raise typer.Exit(code=1)


@catalog_app.command("validate")
def catalog_validate(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Catalog item name, namespaced identifier, or file path to validate."),
    type: Annotated[
        CatalogItemType | None,
        typer.Option("--type", help="Item type to validate against. Required when target is a file path."),
    ] = None,
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Validate a catalog blueprint or step definition without executing it."""
    context: CliContext = ctx.obj["context"]
    result = catalog_validate_command(context, target, item_type=type, output_format=format)
    if result.status in (
        CatalogValidateStatus.NOT_FOUND,
        CatalogValidateStatus.UNREADABLE,
        CatalogValidateStatus.TYPE_REQUIRED,
    ):
        raise typer.Exit(code=2)
    if not result.ok:
        raise typer.Exit(code=1)
