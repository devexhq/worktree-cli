import typer

from .command import workflow_list_command, workflow_resume_command, workflow_run_command, workflow_show_command

workflow_app = typer.Typer(
    name="workflow",
    help="Inspect and manage Worktree workflow definitions and sessions.",
    invoke_without_command=True,
)


@workflow_app.callback(invoke_without_command=True)
def workflow_callback(ctx: typer.Context):
    """Inspect and manage Worktree workflow definitions and sessions."""
    if ctx.invoked_subcommand is None:
        workflow_list_command()


@workflow_app.command("list")
def workflow_list(ctx: typer.Context):
    """List workflow run sessions."""
    workflow_list_command()


@workflow_app.command("show")
def workflow_show(
    id: str = typer.Argument(..., help="Workflow session ID to show."),
):
    """Show details for a specific workflow session."""
    workflow_show_command(id)


@workflow_app.command("run")
def workflow_run(
    name: str = typer.Argument(..., help="Logical workflow name to run."),
):
    """Run a workflow (validates the definition; execution is not implemented yet)."""
    workflow_run_command(name)


@workflow_app.command("resume")
def workflow_resume(
    id: str = typer.Argument(..., help="Workflow session ID to resume."),
):
    """Resume an interrupted workflow session."""
    workflow_resume_command(id)


_SANDBOX_STATUS_OPTION = typer.Option(
    None,
    "--status",
    help="Filter by lifecycle status (active, merged, cleaned, conflict).",
    case_sensitive=False,
)
