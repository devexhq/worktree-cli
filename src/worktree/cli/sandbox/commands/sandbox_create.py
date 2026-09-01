from worktree.cli.context import CliContext
from worktree.core.sandbox import GitSandboxManager

from ..models import SandboxCreateCommandOutcome
from ..renderers import (
    render_sandbox_create_failed,
)


def sandbox_create_command(
    context: CliContext,
    name: str | None = None,
    base_ref: str | None = None,
    wip: bool = False,
    output_format: str = "terminal",
) -> SandboxCreateCommandOutcome:
    """Create an isolated git worktree sandbox.

    Calls ``GitSandboxManager.create_sandbox`` and renders success or a
    classified failure panel.

    Args:
        context: CLI context instance.
        name: Optional human-readable sandbox name.
        base_ref: Optional git ref override for worktree creation.
        wip: When True, overlay uncommitted working-tree changes.
        output_format: Presentation format ("terminal" or "json").
    """
    result = GitSandboxManager(path=context.cwd, db=context.db.sandboxes).create_sandbox(
        name=name,
        base_ref=base_ref,
        include_wip=wip,
    )
    if not result.ok or result.session is None:
        if output_format == "json":
            context.dispatcher.dispatch(result, output_format="json")
        else:
            render_sandbox_create_failed(result.errors, output=context.output)
        return SandboxCreateCommandOutcome(errors=list(result.errors), warnings=list(result.warnings))

    context.dispatcher.dispatch(result, output_format=output_format)
    return SandboxCreateCommandOutcome(
        session_id=result.session.session_id,
        warnings=list(result.warnings),
    )
