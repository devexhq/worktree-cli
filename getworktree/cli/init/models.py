"""Models for the init command."""

from __future__ import annotations

from pydantic import BaseModel

from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.catalog.services.seeder import SeedResult
from getworktree.core.config.generator import ConfigGenerationResult


class InitCommandOutcome(BaseModel):
    """Structured result used for rendering init command output."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    bootstrap_result: BootstrapResult
    config_result: ConfigGenerationResult
    seed_result: SeedResult
