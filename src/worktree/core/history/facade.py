"""History domain facade."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import BlueprintKind, RunsRepository, RunStatus
from worktree.core.engine.services.reconcile import reconcile_stale_runs
from worktree.core.history.models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)


class History:
    """Unified entrypoint for execution run history inspection and retrieval."""

    def __init__(self, path: Path = Path("."), db: RunsRepository | None = None) -> None:
        self.path = path.resolve()
        self.cwd = self.path
        self.db = db if db is not None else RunsRepository(self.path)

    def list(
        self,
        *,
        limit: int | None = 20,
        status: str | None = None,
        kind: str | None = None,
    ) -> HistoryListResult:
        """Retrieve filtered execution runs from database."""
        warnings: list[str] = []
        reconciliation_result = reconcile_stale_runs(self.db, path=self.path)
        if reconciliation_result.warning:
            warnings.append(reconciliation_result.warning)

        status_filter: RunStatus | str | None = None
        if status is not None:
            try:
                status_filter = RunStatus(status.lower())
            except ValueError:
                status_filter = status

        kind_filter: BlueprintKind | str | None = None
        if kind is not None:
            try:
                kind_filter = BlueprintKind(kind.lower())
            except ValueError:
                kind_filter = kind

        runs = self.db.list(limit=limit, status=status_filter, kind=kind_filter)
        return HistoryListResult(status=HistoryListStatus.OK, runs=runs, warnings=warnings)

    def show(self, session_id: str) -> HistoryShowResult:
        """Look up execution session metadata and run details."""
        row = self.db.get(session_id)
        if row is None:
            return HistoryShowResult(status=HistoryShowStatus.NOT_FOUND, session_id=session_id)

        return HistoryShowResult(status=HistoryShowStatus.OK, session_id=session_id, run=row)
