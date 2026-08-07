import typer

from .command import sandbox_create_command, sandbox_delete_command, sandbox_list_command, sandbox_show_command

sandbox_app = typer.Typer(
    name="sandbox",
    help="Inspect and manage git worktree sandboxes.",
)


@sandbox_app.command("create")
def sandbox_create(
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
    sandbox_create_command(name=name, base_ref=base_ref, wip=wip)


@sandbox_app.command("list")
def sandbox_list(
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by lifecycle status (active, merged, cleaned, conflict).",
        case_sensitive=False,
    ),
):
    """List tracked sandboxes and their lifecycle status."""
    sandbox_list_command(status=status.value if status is not None else None)


@sandbox_app.command("show")
def sandbox_show(
    sandbox_id: str = typer.Argument(..., help="Sandbox id to show."),
):
    """Show full detail for one tracked sandbox."""
    sandbox_show_command(sandbox_id)


@sandbox_app.command("delete")
def sandbox_delete(
    sandbox_id: str = typer.Argument(..., help="Sandbox id to delete."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip the confirmation prompt and delete immediately.",
    ),
):
    """Delete a sandbox worktree and branch after confirmation."""
    sandbox_delete_command(sandbox_id, force=force)
