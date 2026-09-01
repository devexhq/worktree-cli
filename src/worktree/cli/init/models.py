"""Models for the init command."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.bootstrap import WorkspaceInitResult


class InitCommandOutcome(BaseModel):
    """Structured outcome returned by init command handler."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    result: WorkspaceInitResult | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when initialization completed without errors."""
        return not self.errors and self.result is not None and self.result.ok
