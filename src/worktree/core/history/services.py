"""Class-based execution services for history operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db import BlueprintKind, RunsRepository, RunStatus

from .models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)
from .renderers import (
    render_history_list,
    render_history_not_found,
    render_history_show,
    render_not_initialized,
)


@dataclass
class HistoryListService:
    """Service encapsulating execution history retrieval and rendering."""

    path: Path
    db: RunsRepository
    output: RichOutput
    limit: int | None = 20
    status: str | None = None
    kind: str | None = None

    def collect(self) -> HistoryListResult:
        """Load configuration and retrieve filtered execution runs from database."""
        load = load_config_result(path=self.path)
        if not load.ok:
            return HistoryListResult(
                status=HistoryListStatus.NOT_INITIALIZED,
                errors=list(load.errors),
            )

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
        return HistoryListResult(status=HistoryListStatus.OK, runs=runs)

    def execute(self) -> HistoryListResult:
        """Execute history list query and render results to console."""
        result = self.collect()
        if result.status is HistoryListStatus.NOT_INITIALIZED:
            render_not_initialized(result.errors, output=self.output)
            return result

        render_history_list(result.runs, output=self.output)
        return result


@dataclass
class HistoryShowService:
    """Service encapsulating history session inspection and rendering."""

    session_id: str
    path: Path
    db: RunsRepository
    output: RichOutput

    def collect(self) -> HistoryShowResult:
        """Look up execution session metadata, errors, and checkpoint contents."""
        load = load_config_result(path=self.path)
        if not load.ok:
            return HistoryShowResult(
                status=HistoryShowStatus.NOT_INITIALIZED,
                errors=list(load.errors),
            )

        row = self.db.get(self.session_id)

        if row is None:
            return HistoryShowResult(status=HistoryShowStatus.NOT_FOUND)

        return HistoryShowResult(status=HistoryShowStatus.OK, run=row)

    def execute(self) -> HistoryShowResult:
        """Execute session show query and render results to console."""
        result = self.collect()
        if result.status is HistoryShowStatus.NOT_INITIALIZED:
            render_not_initialized(result.errors, output=self.output)
            return result

        if result.status is HistoryShowStatus.NOT_FOUND or result.run is None:
            render_history_not_found(self.session_id, output=self.output)
            return result

        render_history_show(result.run, output=self.output)
        return result
