"""Models for the init command."""

from __future__ import annotations

from pydantic import BaseModel

from worktree.core.bootstrap import BootstrapResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class InitCommandOutcome(BaseModel):
    """Structured result used for rendering init command output."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    bootstrap_result: BootstrapResult
    config_result: ConfigGenerationResult
    seed_result: SeedResult
