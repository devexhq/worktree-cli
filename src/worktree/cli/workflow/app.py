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


@workflow_app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def workflow_run(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Logical workflow name to run."),
    no_sandbox: bool = typer.Option(
        False,
        "--no-sandbox",
        help="Run execution in-place in the working tree without creating a Git sandbox.",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        help="Retain sandbox worktree after workflow completion.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Override default target agent adapter.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Explicit session identifier.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable interactive prompts; prompt_user failures abort the run.",
    ),
):
    """Run a workflow blueprint."""
    workflow_run_command(
        name,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=list(ctx.args),
        non_interactive=non_interactive,
    )


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
