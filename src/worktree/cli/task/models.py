"""Outcome models for task CLI commands."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.db import RunRecord


class TaskListCommandOutcome(BaseModel):
    """Outcome for ``wt task list`` (or default ``wt task``)."""

    model_config = {"extra": "forbid", "strict": True}

    runs: list[RunRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if no errors were encountered."""
        return len(self.errors) == 0
