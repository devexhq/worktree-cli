"""Models for the bootstrap and workspace initialization domain."""

from __future__ import annotations

from enum import Enum, StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from worktree.common.models import BaseResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class DirEnsureOutcome(Enum):
    """Result of attempting to ensure a directory exists."""

    CREATED = "created"
    EXISTING = "existing"


class BootstrapOutcome(StrEnum):
    """Classified outcome of bootstrapping the .worktree/ directory structure."""

    INITIALIZED = "initialized"
    REPAIRED = "repaired"
    ALREADY_INITIALIZED = "already_initialized"
    FAILED = "failed"


class InitFailureMode(StrEnum):
    """Failure mode classification for workspace initialization."""

    PREFLIGHT = "preflight"
    BOOTSTRAP = "bootstrap"
    CONFIG_GENERATION = "config_generation"


class BootstrapResult(BaseResult):
    """Outcome of bootstrapping the `.worktree/` directory tree."""

    root_path: Path
    outcome: BootstrapOutcome = BootstrapOutcome.INITIALIZED
    root_created: bool = False
    dirs_created: list[Path] = Field(default_factory=list)
    dirs_existing: list[Path] = Field(default_factory=list)
    repaired: bool = False
    seed_result: SeedResult = Field(default_factory=SeedResult)

    @property
    def ok(self) -> bool:
        """True when bootstrap completed without errors."""
        return not self.errors

    @model_validator(mode="after")
    def _resolve_outcome(self) -> Self:
        """Derive outcome from state booleans if not explicitly specified."""
        if self.errors:
            self.outcome = BootstrapOutcome.FAILED
        elif "outcome" not in self.model_fields_set:
            if self.repaired:
                self.outcome = BootstrapOutcome.REPAIRED
            elif self.root_created or self.dirs_created:
                self.outcome = BootstrapOutcome.INITIALIZED
            else:
                self.outcome = BootstrapOutcome.ALREADY_INITIALIZED
        return self


class WorkspaceInitResult(BaseResult):
    """Structured outcome of initializing a project workspace."""

    bootstrap_result: BootstrapResult | None = None
    config_result: ConfigGenerationResult | None = None
    seed_result: SeedResult | None = None
    failure_mode: InitFailureMode | None = None

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

    @model_validator(mode="after")
    def _resolve_failure_mode(self) -> Self:
        """Derive failure mode from child results when not explicitly provided."""
        if "failure_mode" not in self.model_fields_set:
            if self.bootstrap_result is None and self.errors:
                self.failure_mode = InitFailureMode.PREFLIGHT
            elif self.bootstrap_result is not None and not self.bootstrap_result.ok:
                self.failure_mode = InitFailureMode.BOOTSTRAP
            elif self.config_result is not None and not self.config_result.ok:
                self.failure_mode = InitFailureMode.CONFIG_GENERATION
        return self
