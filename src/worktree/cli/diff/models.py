"""CLI outcome models for ``wt diff``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.diff.models import DiffResult


class DiffCommandOutcome(BaseModel):
    """Execution outcome for wt diff command."""

    model_config = {"extra": "forbid", "strict": True}

    result: DiffResult | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when result is ok and no fatal errors occurred."""
        return self.result is not None and self.result.ok and not self.errors
