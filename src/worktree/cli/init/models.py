"""Models for the init command."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.bootstrap import BootstrapResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class InitCommandOutcome(BaseModel):
    """Structured result used for rendering init command output."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    bootstrap_result: BootstrapResult | None = None
    config_result: ConfigGenerationResult | None = None
    seed_result: SeedResult | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when bootstrap, config, and catalog seeding all succeed with no errors."""
        return (
            not self.errors
            and self.bootstrap_result is not None
            and self.bootstrap_result.ok
            and self.config_result is not None
            and self.config_result.ok
            and self.seed_result is not None
            and self.seed_result.ok
        )
