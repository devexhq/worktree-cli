"""Typer CLI entrypoint for the Worktree (`wt`) command."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from getworktree.cli.catalog.app import catalog_app
from getworktree.cli.config.app import config_app
from getworktree.cli.init.app import init_app
from getworktree.cli.sandbox.app import sandbox_app
from getworktree.cli.task.app import task_app
from getworktree.cli.template.app import template_app
from getworktree.cli.workflow.app import workflow_app
from getworktree.commands.catalog.command import (
    catalog_create_command,
    catalog_delete_command,
    catalog_list_command,
    catalog_show_command,
)
from getworktree.common.version import get_version

# Initialize a central styling console for high-utility layout parsing
console = Console()

# Package Metadata matching our PyPI footprint
__version__ = get_version()

# Initialize Typer App with clean configuration defaults
app = typer.Typer(
    name="wt",
    help="Isolated git worktree developer workflows and autonomous AI agent workspaces.",
    add_completion=True,
    rich_markup_mode="rich",
)

app.add_typer(init_app, name="init")

app.add_typer(config_app, name="config")

app.add_typer(workflow_app, name="workflow")

app.add_typer(sandbox_app, name="sandbox")

app.add_typer(template_app, name="template")

app.add_typer(catalog_app, name="catalog")

app.add_typer(task_app, name="task")


def print_welcome_banner():
    """Renders a highly scannable, developer-focused ASCII brand panel."""
    banner_text = Text()
    banner_text.append("🌳 Worktree CLI ", style="bold green")
    banner_text.append(f"v{__version__}\n", style="dim cyan")
    banner_text.append("Isolated Git Workspaces & Agent Workflows", style="italic dim")

    console.print(Panel(banner_text, border_style="green", expand=False, padding=(1, 4)))


def version_callback(value: bool):
    """Callback function to handle explicit version printing flags."""
    if value:
        console.print(f"[bold green]Worktree CLI[/bold green] v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable extensive internal engineering telemetry logging.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print the current version of the Worktree CLI and exit.",
    ),
):
    """Global configuration wrapper managing shared application context."""
    # Stash verbose settings inside the runtime context dict for downstream commands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # If the developer types just 'wt' without a subcommand, render banner and help
    if ctx.invoked_subcommand is None:
        print_welcome_banner()
        console.print(ctx.get_help())
        raise typer.Exit()
    elif verbose:
        console.print("[dim yellow][TELEMETRY] Global verbose tracking layer active.[/dim yellow]")


_CATALOG_TYPE_OPTION = typer.Option(
    None,
    "--type",
    help="Filter catalog blueprints by type (workflow, task, step).",
)


@catalog_app.callback(invoke_without_command=True)
def catalog_callback(
    ctx: typer.Context,
    type: str | None = _CATALOG_TYPE_OPTION,
):
    """Inspect and manage executable blueprints in .worktree/catalog/."""
    if ctx.invoked_subcommand is None:
        outcome = catalog_list_command(type_filter=type)
        if not outcome.ok:
            raise typer.Exit(code=1)


@catalog_app.command("list")
def catalog_list(
    ctx: typer.Context,
    type: str | None = _CATALOG_TYPE_OPTION,
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
    template: str | None = typer.Option(
        None,
        "--template",
        help="Optional built-in template name to populate content from.",
    ),
):
    """Create a new catalog blueprint under .worktree/catalog/<type>s/<name>.yml."""
    outcome = catalog_create_command(item_type=type, name=name, template=template)
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
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete catalog blueprint '{name}'?")
        if not confirm:
            console.print("Deletion cancelled.")
            raise typer.Exit()

    outcome = catalog_delete_command(sha_or_name=name)
    if not outcome.ok:
        raise typer.Exit(code=1)


# @task_app.callback(invoke_without_command=True)
# def task_callback(ctx: typer.Context):
#     """Inspect and execute task blueprints."""
#     if ctx.invoked_subcommand is None:
#         outcome = task_list_command()
#         if not outcome.ok:
#             raise typer.Exit(code=1)


# @task_app.command("list")
# def task_list(ctx: typer.Context):
#     """List available task blueprints."""
#     outcome = task_list_command()
#     if not outcome.ok:
#         raise typer.Exit(code=1)


# @task_app.command("show")
# def task_show(
#     ctx: typer.Context,
#     name: str = typer.Argument(..., help="Task blueprint name or SHA to show."),
# ):
#     """Show metadata and definition content of a task blueprint."""
#     outcome = task_show_command(name=name)
#     if not outcome.ok:
#         raise typer.Exit(code=1)


# @task_app.command("run")
# def task_run(
#     name: str = typer.Argument(..., help="Task blueprint name to run."),
#     no_sandbox: bool = typer.Option(
#         False,
#         "--no-sandbox",
#         help="Run execution in-place in the working tree without creating a Git sandbox.",
#     ),
#     keep: bool = typer.Option(
#         False,
#         "--keep",
#         help="Retain sandbox worktree after task completion.",
#     ),
#     agent: str | None = typer.Option(
#         None,
#         "--agent",
#         help="Override default target agent adapter.",
#     ),
# ):
#     """Run a task blueprint."""
#     outcome = task_run_command(
#         name=name,
#         no_sandbox=no_sandbox,
#         keep=keep,
#         agent=agent,
#     )
#     if not outcome.ok:
#         raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
