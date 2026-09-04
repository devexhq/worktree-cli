"""Class-based execution services for history operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worktree.core.db import BlueprintKind, RunsRepository, RunStatus
from worktree.core.engine.services.reconcile import reconcile_stale_runs

from .models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)


@dataclass
class HistoryListService:
    """Service encapsulating execution history retrieval."""

    path: Path
    db: RunsRepository
    limit: int | None = 20
    status: str | None = None
    kind: str | None = None

    def collect(self) -> HistoryListResult:
        """Retrieve filtered execution runs from database."""
        warnings: list[str] = []
        reconciliation_result = reconcile_stale_runs(self.db, path=self.path)
        if reconciliation_result.warning:
            warnings.append(reconciliation_result.warning)

        status_filter: RunStatus | str | None = None
        if self.status is not None:
            try:
                status_filter = RunStatus(self.status.lower())
            except ValueError:
                status_filter = self.status

        kind_filter: BlueprintKind | str | None = None
        if self.kind is not None:
            try:
                kind_filter = BlueprintKind(self.kind.lower())
            except ValueError:
                kind_filter = self.kind

        runs = self.db.list(limit=self.limit, status=status_filter, kind=kind_filter)
        return HistoryListResult(status=HistoryListStatus.OK, runs=runs, warnings=warnings)

    def execute(self) -> HistoryListResult:
        """Execute history list query and return structured result."""
        return self.collect()


@dataclass
class HistoryShowService:
    """Service encapsulating history session inspection."""

    session_id: str
    path: Path
    db: RunsRepository

    def collect(self) -> HistoryShowResult:
        """Look up execution session metadata, errors, and checkpoint contents."""
        row = self.db.get(self.session_id)

        if row is None:
            return HistoryShowResult(
                status=HistoryShowStatus.NOT_FOUND,
                session_id=self.session_id,
                errors=[f"Session '{self.session_id}' not found."],
                fixes=["Run `wt history` to view past sessions"],
            )

        return HistoryShowResult(status=HistoryShowStatus.OK, session_id=self.session_id, run=row)

    def execute(self) -> HistoryShowResult:
        """Execute session show query and return structured result."""
        return self.collect()
