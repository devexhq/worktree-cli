from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.sandbox import Sandbox

from ..models import SandboxCreateCommandOutcome


def sandbox_create_command(
    context: CliContext,
    name: str | None = None,
    base_ref: str | None = None,
    wip: bool = False,
    output_format: str = "terminal",
) -> SandboxCreateCommandOutcome:
    """Create an isolated git worktree sandbox.

    Args:
        context: CLI context instance.
        name: Optional human-readable sandbox name.
        base_ref: Optional git ref override for worktree creation.
        wip: When True, overlay uncommitted working-tree changes.
        output_format: Presentation format ("terminal" or "json").
    """
    result = Sandbox(path=context.cwd, db=context.db.sandboxes).create(
        name=name,
        base_ref=base_ref,
        include_wip=wip,
    )
    ui_dispatcher.dispatch(result, output_format=output_format)
    if not result.ok or result.session is None:
        return SandboxCreateCommandOutcome(errors=list(result.errors), warnings=list(result.warnings))

    return SandboxCreateCommandOutcome(
        session_id=result.session.session_id,
        warnings=list(result.warnings),
    )
