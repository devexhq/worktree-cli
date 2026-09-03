import typer

from worktree.cli.context import CliContext

from .commands.catalog_create import catalog_create_command
from .commands.catalog_delete import catalog_delete_command
from .commands.catalog_list import catalog_list_command
from .commands.catalog_show import catalog_show_command
from .formatters import register_catalog_formatters

register_catalog_formatters()

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
        help="Filter catalog blueprints by type (workflow, task, step).",
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
        help="Filter catalog blueprints by type (workflow, task, step).",
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
    type: str = typer.Argument(..., help="Blueprint item type (workflow, task, step)."),
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
