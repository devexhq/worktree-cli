"""Status CLI models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.config.models import WorktreeConfig


class WorktreeContext(BaseModel):
    """Config plus live Git branch and aggregated warnings."""

    model_config = {"extra": "forbid", "strict": True}

    config: WorktreeConfig
    current_branch: str
    warnings: list[str] = Field(default_factory=list)


class StatusCommandOutcome(BaseModel):
    """Structured outcome for wt status command."""

    model_config = {"extra": "forbid", "strict": True}

    context: WorktreeContext | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if status context loaded without errors."""
        return not self.errors and self.context is not None
