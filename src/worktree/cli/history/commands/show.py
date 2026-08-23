from worktree.cli.context import Context
from worktree.core.history import HistoryShowResult, HistoryShowService


def history_show_command(
    session_id: str,
    *,
    context: Context,
) -> HistoryShowResult:
    """Execute session show query and render results to console."""
    return HistoryShowService(
        session_id=session_id,
        path=context.cwd,
        db=context.db.runs,
        output=context.output,
    ).execute()
