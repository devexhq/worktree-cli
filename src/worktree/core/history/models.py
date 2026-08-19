"""Outcome models for history operations."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from worktree.core.db import RunRecord


class HistoryListStatus(StrEnum):
    """Classified outcome for listing execution history."""

    OK = "ok"
    NOT_INITIALIZED = "not_initialized"


class HistoryListResult(BaseModel):
    """Structured result for history list before rendering."""

    model_config = {"extra": "forbid", "strict": True}

    status: HistoryListStatus
    runs: list[RunRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when listing can proceed (including empty tables)."""
        return self.status == HistoryListStatus.OK and not self.errors


class HistoryShowStatus(StrEnum):
    """Classified outcome for showing history session detail."""

    OK = "ok"
    NOT_INITIALIZED = "not_initialized"
    NOT_FOUND = "not_found"


class HistoryShowResult(BaseModel):
    """Structured result for history show before rendering."""

    model_config = {"extra": "forbid", "strict": True}

    status: HistoryShowStatus
    run: RunRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when a run record is available to render."""
        return self.status == HistoryShowStatus.OK and self.run is not None and not self.errors
