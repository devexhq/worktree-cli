from worktree.common.utils import RichOutput
from worktree.core.config.models import CliContext
from worktree.core.history import HistoryListResult, HistoryListService


def history_root_command(
    *,
    cli_ctx: CliContext,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
    output: RichOutput | None = None,
) -> HistoryListResult:
    """Execute history list query and render results to console."""
    return HistoryListService(
        cli_ctx=cli_ctx,
        limit=limit,
        status=status,
        kind=kind,
        output=output or RichOutput(),
    ).execute()
