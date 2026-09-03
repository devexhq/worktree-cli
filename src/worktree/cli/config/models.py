"""Config CLI models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from worktree.core.config.loader import ConfigLoadResult
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.validate import ConfigValidationResult


class ConfigShowCommandOutcome(BaseModel):
    """Outcome of wt config show command."""

    model_config = {"extra": "forbid", "strict": True}

    result: ConfigLoadResult | None = None
    config: WorktreeConfig | None = None
    config_path: Path | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if config was loaded without errors."""
        if self.result is not None:
            return self.result.ok and not self.errors
        return not self.errors and self.config is not None


class ConfigSetCommandOutcome(BaseModel):
    """Outcome of wt config set command."""

    model_config = {"extra": "forbid", "strict": True}

    key: str | None = None
    value: object = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if config key was updated without errors."""
        return not self.errors and self.key is not None


class ConfigValidateCommandOutcome(BaseModel):
    """Outcome of wt config validate command."""

    model_config = {"extra": "forbid", "strict": True}

    result: ConfigValidationResult | None = None
    config_path: Path | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if config is valid without errors."""
        if self.result is not None:
            return self.result.ok and not self.errors
        return not self.errors and self.config_path is not None
