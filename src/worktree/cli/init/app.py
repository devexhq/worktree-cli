import typer

from worktree.cli.context import CliContext
from worktree.common.filesystem import Filesystem
from worktree.common.utils import RichOutput
from worktree.common.version import get_version
from worktree.core.db.facade import WorktreeDb

from .commands.root import init_command
from .formatters import register_init_formatters

register_init_formatters()

init_app = typer.Typer(name="init", help="Initialize Worktree CLI in the current directory.")


@init_app.callback(invoke_without_command=True)
def init_callback(
    ctx: typer.Context,
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing config with fresh V1 defaults (destructive).",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Add missing required config keys without overwriting user values.",
    ),
    format: str = typer.Option(
        "terminal",
        "--format",
        help="Presentation format ('terminal' or 'json').",
    ),
):
    """Provision a secure local hidden folder path and tracking schemas."""
    target_path = ctx.obj.get("path") if ctx.obj else None
    fs = Filesystem(target_path)
    cwd = fs.root_dir
    context = CliContext(cwd=cwd, db=WorktreeDb(path=cwd), output=RichOutput(), fs=fs)
    outcome = init_command(
        context,
        tool_version=get_version(),
        overwrite=overwrite,
        repair=repair,
        output_format=format,
    )
    if not outcome.ok:
        raise typer.Exit(code=1)
