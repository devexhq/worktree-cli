"""Command outcome models for wt resume."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.blueprint.models import BlueprintRunResult
from worktree.core.db import RunRecord

__all__ = ["BlueprintResumeOutcome"]


class BlueprintResumeOutcome(BaseModel):
    """Outcome of running ``wt resume``."""

    model_config = {"extra": "forbid", "strict": True}

    result: BlueprintRunResult | None = None
    run_record: RunRecord | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if resume completed without errors."""
        return not self.errors and (self.result is None or self.result.ok)
