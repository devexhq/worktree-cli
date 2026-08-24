from typing import Annotated

import typer

from worktree.cli.context import CliContext
from worktree.core.db import SandboxStatus

from .commands.sandbox_create import sandbox_create_command
from .commands.sandbox_delete import sandbox_delete_command
from .commands.sandbox_list import sandbox_list_command
from .commands.sandbox_show import sandbox_show_command

sandbox_app = typer.Typer(
    name="sandbox",
    help="Inspect and manage git worktree sandboxes.",
)


@sandbox_app.command("create")
def sandbox_create(
    ctx: typer.Context,
    name: str | None = typer.Option(
        None,
        "--name",
        help="Optional human-readable name for the sandbox.",
    ),
    base_ref: str | None = typer.Option(
        None,
        "--base-ref",
        help=("Git ref to base the sandbox on. When omitted, uses the current branch or config sandbox.base_ref."),
    ),
    wip: bool = typer.Option(
        False,
        "--wip/--no-wip",
        help=("Include uncommitted working-tree changes in the sandbox (tracked + untracked; not ignored)."),
    ),
):
    """Create an isolated git worktree sandbox."""
    context: CliContext = ctx.obj["context"]
    outcome = sandbox_create_command(context, name=name, base_ref=base_ref, wip=wip)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)


@sandbox_app.command("list")
def sandbox_list(
    ctx: typer.Context,
    status: Annotated[
        SandboxStatus | None,
        typer.Option(
            "--status",
            help="Filter by lifecycle status (active, merged, cleaned, conflict).",
            case_sensitive=False,
        ),
    ] = None,
):
    """List tracked sandboxes and their lifecycle status."""
    context: CliContext = ctx.obj["context"]
    outcome = sandbox_list_command(context, status=status.value if status is not None else None)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)


@sandbox_app.command("show")
def sandbox_show(
    ctx: typer.Context,
    sandbox_id: str = typer.Argument(..., help="Sandbox id to show."),
):
    """Show full detail for one tracked sandbox."""
    context: CliContext = ctx.obj["context"]
    outcome = sandbox_show_command(context, sandbox_id)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)


@sandbox_app.command("delete")
def sandbox_delete(
    ctx: typer.Context,
    sandbox_id: str = typer.Argument(..., help="Sandbox id to delete."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip the confirmation prompt and delete immediately.",
    ),
):
    """Delete a sandbox worktree and branch after confirmation."""
    context: CliContext = ctx.obj["context"]
    outcome = sandbox_delete_command(context, sandbox_id, force=force)
    context.output.print()
    if not outcome.ok:
        raise typer.Exit(code=1)
