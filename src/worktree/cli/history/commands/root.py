from worktree.cli.context import CliContext
from worktree.core.history import HistoryListResult
from worktree.core.history.services import HistoryListService


def history_root_command(
    context: CliContext,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
) -> HistoryListResult:
    """Execute history list query and render results to console."""
    return HistoryListService(
        path=context.cwd,
        db=context.db.runs,
        output=context.output,
        limit=limit,
        status=status,
        kind=kind,
    ).execute()
