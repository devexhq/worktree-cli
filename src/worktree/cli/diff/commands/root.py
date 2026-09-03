"""Root command implementation for ``wt diff`` (pure Python handler, zero Typer imports)."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.diff import Diff, DiffResult


def diff_command(
    context: CliContext,
    session_id: str | None = None,
    *,
    raw: bool = False,
    full: bool = False,
    max_lines: int | None = None,
    output_format: str = "terminal",
) -> DiffResult:
    """Execute session diff query and render results via UI dispatcher.

    Args:
        context: CLI execution context holding cwd and Rich output builder.
        session_id: Optional session identifier. When omitted, latest session is resolved.
        raw: When True, outputs unformatted plain text patch directly to stdout.
        full: When True, bypasses truncation in interactive terminals.
        max_lines: Optional custom line truncation threshold for testing or programmatic overrides.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        Structured DiffResult with status, errors, and warnings.
    """
    result = Diff(path=context.cwd).inspect(session_id=session_id)
    result.raw = raw
    result.full = full
    result.max_lines = max_lines
    ui_dispatcher.dispatch(result, output_format)
    return result
