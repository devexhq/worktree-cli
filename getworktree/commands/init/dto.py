"""DTOs for the init command."""

from __future__ import annotations

from dataclasses import dataclass

from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.config.generator import ConfigGenerationResult
from getworktree.core.loops.seeder import LoopSeedResult


@dataclass
class InitCommandOutcome:
    """Structured result used for rendering init command output."""

    bootstrap_result: BootstrapResult
    config_result: ConfigGenerationResult
    loop_seed_result: LoopSeedResult
