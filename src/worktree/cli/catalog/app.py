import typer

from .command import catalog_create_command, catalog_delete_command, catalog_list_command, catalog_show_command

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
):
    """Inspect and manage executable blueprints in .worktree/catalog/."""
    if ctx.invoked_subcommand is None:
        outcome = catalog_list_command(type_filter=type)
        if not outcome.ok:
            raise typer.Exit(code=1)


@catalog_app.command("list")
def catalog_list(
    ctx: typer.Context,
    type: str | None = typer.Option(
        None,
        "--type",
        help="Filter catalog blueprints by type (workflow, task, step).",
    ),
):
    """List catalog blueprints."""
    outcome = catalog_list_command(type_filter=type)
    if not outcome.ok:
        raise typer.Exit(code=1)


@catalog_app.command("create")
def catalog_create(
    ctx: typer.Context,
    type: str = typer.Argument(..., help="Blueprint item type (workflow, task, step)."),
    name: str = typer.Option(..., "--name", help="Name for the catalog blueprint file."),
):
    """Create a new catalog blueprint under .worktree/catalog/<type>s/<name>.yml."""
    outcome = catalog_create_command(item_type=type, name=name)
    if not outcome.ok:
        raise typer.Exit(code=1)


@catalog_app.command("show")
def catalog_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Catalog blueprint SHA or name to show."),
):
    """Show metadata and definition content of a catalog blueprint."""
    outcome = catalog_show_command(sha_or_name=name)
    if not outcome.ok:
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
):
    """Delete a catalog blueprint file and its database index record."""
    outcome = catalog_delete_command(sha_or_name=name, force=force)
    if not outcome.ok:
        raise typer.Exit(code=1)
