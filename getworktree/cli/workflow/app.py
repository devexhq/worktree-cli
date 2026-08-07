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
    max_attempts: int | None = typer.Option(
        None,
        "--max-attempts",
        help="Override effective max attempts (>= 1).",
        min=1,
    ),
    keep: bool = typer.Option(
        False,
        "--keep/--no-keep",
        help="When --keep, force retain the sandbox (auto_clean=False).",
    ),
    approve_each: bool | None = typer.Option(
        None,
        "--approve-each/--no-approve-each",
        help="Require (or skip) approval before each patch apply.",
    ),
    wip: bool = typer.Option(
        False,
        "--wip/--no-wip",
        help=("Include uncommitted working-tree changes in the sandbox (tracked + untracked; not ignored)."),
    ),
    dump_prompt: bool = typer.Option(
        False,
        "--dump-prompt/--no-dump-prompt",
        help=("Dump provider-specific agent input to /tmp before each agent call (debugging aid)."),
    ),
    no_sandbox: bool = typer.Option(
        False,
        "--no-sandbox",
        help="Run execution in-place in the working tree without creating a Git sandbox.",
    ),
):
    """Run a workflow in an isolated git worktree sandbox."""
    workflow_run_command(
        name,
        max_attempts=max_attempts,
        keep=keep if keep else None,
        approve_each=approve_each,
        wip=wip,
        dump_prompt=dump_prompt,
        no_sandbox=no_sandbox,
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
