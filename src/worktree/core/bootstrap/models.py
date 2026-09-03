"""Models for the bootstrap and workspace initialization domain."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field

from worktree.common.models import BaseResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class DirEnsureOutcome(Enum):
    """Result of attempting to ensure a directory exists."""

    CREATED = "created"
    EXISTING = "existing"


class BootstrapResult(BaseResult):
    """Outcome of bootstrapping the `.worktree/` directory tree."""

    root_path: Path
    root_created: bool = False
    dirs_created: list[Path] = Field(default_factory=list)
    dirs_existing: list[Path] = Field(default_factory=list)
    repaired: bool = False
    seed_result: SeedResult = Field(default_factory=SeedResult)

    @property
    def ok(self) -> bool:
        """True when bootstrap completed without errors."""
        return not self.errors


class WorkspaceInitResult(BaseResult):
    """Structured outcome of initializing a project workspace."""

    bootstrap_result: BootstrapResult | None = None
    config_result: ConfigGenerationResult | None = None
    seed_result: SeedResult | None = None

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
