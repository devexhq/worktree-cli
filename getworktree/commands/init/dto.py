"""DTOs for the init command."""

from __future__ import annotations

from pydantic import BaseModel

from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.config.generator import ConfigGenerationResult
from getworktree.core.loops.seeder import LoopSeedResult


class InitCommandOutcome(BaseModel):
    """Structured result used for rendering init command output."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    bootstrap_result: BootstrapResult
    config_result: ConfigGenerationResult
    loop_seed_result: LoopSeedResult
