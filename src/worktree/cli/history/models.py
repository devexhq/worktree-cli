"""Command outcome models for wt history subcommands."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.db import RunRecord
from worktree.core.history.models import HistoryListResult, HistoryShowResult

__all__ = [
    "HistoryListCommandOutcome",
    "HistoryShowCommandOutcome",
]


class HistoryListCommandOutcome(BaseModel):
    """Outcome of running ``wt history`` or ``wt history list``."""

    model_config = {"extra": "forbid", "strict": True}

    result: HistoryListResult | None = None
    runs: list[RunRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if list operation completed without errors."""
        return not self.errors and (self.result is not None and self.result.ok)


class HistoryShowCommandOutcome(BaseModel):
    """Outcome of running ``wt history show``."""

    model_config = {"extra": "forbid", "strict": True}

    result: HistoryShowResult | None = None
    run: RunRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if session record was found and rendered."""
        return not self.errors and (self.run is not None or (self.result is not None and self.result.ok))
