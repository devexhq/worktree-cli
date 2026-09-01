from worktree.cli.context import CliContext
from worktree.core.history import HistoryShowResult
from worktree.core.history.services import HistoryShowService


def history_show_command(
    context: CliContext,
    session_id: str,
) -> HistoryShowResult:
    """Execute session show query and render results to console."""
    return HistoryShowService(
        session_id=session_id,
        path=context.cwd,
        db=context.db.runs,
        output=context.output,
    ).execute()
