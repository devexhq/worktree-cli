"""Status CLI models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.status.models import WorktreeStatusResult


class StatusCommandOutcome(BaseModel):
    """Structured outcome for wt status command."""

    model_config = {"extra": "forbid", "strict": True}

    result: WorktreeStatusResult | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if status context loaded without errors."""
        return not self.errors and self.result is not None
