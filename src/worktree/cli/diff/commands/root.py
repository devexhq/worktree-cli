"""Root command implementation for ``wt diff`` (pure Python handler, zero Typer imports)."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.diff import DiffResult, DiffService


def diff_command(
    context: CliContext,
    session_id: str | None = None,
    *,
    raw: bool = False,
    full: bool = False,
    max_lines: int | None = None,
) -> DiffResult:
    """Execute session diff query and render results to console.

    Args:
        context: CLI execution context holding cwd and Rich output builder.
        session_id: Optional session identifier. When omitted, latest session is resolved.
        raw: When True, outputs unformatted plain text patch directly to stdout.
        full: When True, bypasses truncation in interactive terminals.
        max_lines: Optional custom line truncation threshold for testing or programmatic overrides.

    Returns:
        Structured DiffResult with status, diff text, and artifact path.
    """
    return DiffService(
        path=context.cwd,
        output=context.output,
        session_id=session_id,
        raw=raw,
        full=full,
        max_lines=max_lines,
    ).execute()
