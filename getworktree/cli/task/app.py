import typer

from .command import task_list_command, task_run_command, task_show_command

task_app = typer.Typer(
    name="task",
    help="Inspect and execute task blueprints.",
    invoke_without_command=True,
)


@task_app.callback(invoke_without_command=True)
def task_callback(ctx: typer.Context):
    """Inspect and execute task blueprints."""
    if ctx.invoked_subcommand is None:
        outcome = task_list_command()
        if not outcome.ok:
            raise typer.Exit(code=1)


@task_app.command("list")
def task_list(ctx: typer.Context):
    """List available task blueprints."""
    outcome = task_list_command()
    if not outcome.ok:
        raise typer.Exit(code=1)


@task_app.command("show")
def task_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Task blueprint name or SHA to show."),
):
    """Show metadata and definition content of a task blueprint."""
    outcome = task_show_command(name=name)
    if not outcome.ok:
        raise typer.Exit(code=1)


@task_app.command("run")
def task_run(
    name: str = typer.Argument(..., help="Task blueprint name to run."),
    no_sandbox: bool = typer.Option(
        False,
        "--no-sandbox",
        help="Run execution in-place in the working tree without creating a Git sandbox.",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        help="Retain sandbox worktree after task completion.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Override default target agent adapter.",
    ),
):
    """Run a task blueprint."""
    outcome = task_run_command(
        name=name,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
    )
    if not outcome.ok:
        raise typer.Exit(code=1)
