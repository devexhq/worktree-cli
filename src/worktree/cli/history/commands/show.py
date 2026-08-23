from worktree.common.utils import RichOutput
from worktree.core.config.models import CliContext
from worktree.core.history import HistoryShowResult, HistoryShowService


def history_show_command(
    session_id: str,
    *,
    cli_ctx: CliContext,
    output: RichOutput | None = None,
) -> HistoryShowResult:
    """Execute session show query and render results to console."""
    return HistoryShowService(
        session_id=session_id,
        cli_ctx=cli_ctx,
        output=output or RichOutput(),
    ).execute()
