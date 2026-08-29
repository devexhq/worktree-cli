from worktree.cli.context import CliContext
from worktree.core.sandbox import GitSandboxManager

from ..models import SandboxCreateCommandOutcome
from ..renderers import (
    render_sandbox_create_failed,
    render_sandbox_create_success,
)


def sandbox_create_command(
    context: CliContext,
    name: str | None = None,
    base_ref: str | None = None,
    wip: bool = False,
) -> SandboxCreateCommandOutcome:
    """Create an isolated git worktree sandbox.

    Calls ``GitSandboxManager.create_sandbox`` and renders success or a
    classified failure panel.

    Args:
        name: Optional human-readable sandbox name.
        base_ref: Optional git ref override for worktree creation.
        wip: When True, overlay uncommitted working-tree changes.
        context: CLI context instance.
    """
    result = GitSandboxManager(path=context.cwd, db=context.db.sandboxes).create_sandbox(
        name=name,
        base_ref=base_ref,
        include_wip=wip,
    )
    if not result.ok or result.session is None:
        render_sandbox_create_failed(result.errors, output=context.output)
        return SandboxCreateCommandOutcome(errors=list(result.errors), warnings=list(result.warnings))

    render_sandbox_create_success(
        result.session,
        warnings=result.warnings,
        cwd=context.cwd,
        output=context.output,
    )
    return SandboxCreateCommandOutcome(
        session_id=result.session.session_id,
        warnings=list(result.warnings),
    )
