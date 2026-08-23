from worktree.cli.context import Context
from worktree.common.utils import RichOutput
from worktree.core.history import HistoryListResult, HistoryListService


def history_root_command(
    *,
    context: Context,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
    output: RichOutput | None = None,
) -> HistoryListResult:
    """Execute history list query and render results to console."""
    return HistoryListService(
        path=context.cwd,
        db=context.db.runs,
        limit=limit,
        status=status,
        kind=kind,
        output=output or RichOutput(),
    ).execute()
