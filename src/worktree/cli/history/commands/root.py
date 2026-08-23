from worktree.cli.context import Context
from worktree.core.history import HistoryListResult, HistoryListService


def history_root_command(
    *,
    context: Context,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
) -> HistoryListResult:
    """Execute history list query and render results to console."""
    service = HistoryListService(
        path=context.cwd,
        db=context.db.runs,
        output=context.output,
        limit=limit,
        status=status,
        kind=kind,
    )
    result = service.execute()
    context.output.print()
    return result
