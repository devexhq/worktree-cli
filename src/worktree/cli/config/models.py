"""Config CLI models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from worktree.core.config.models import WorktreeConfig


class ConfigShowCommandOutcome(BaseModel):
    """Outcome of wt config show command."""

    model_config = {"extra": "forbid", "strict": True}

    ok: bool
    config: WorktreeConfig | None = None
    config_path: Path | None = None
    errors: list[str] = Field(default_factory=list)


class ConfigSetCommandOutcome(BaseModel):
    """Outcome of wt config set command."""

    model_config = {"extra": "forbid", "strict": True}

    ok: bool
    key: str | None = None
    value: object = None
    errors: list[str] = Field(default_factory=list)


class ConfigValidateCommandOutcome(BaseModel):
    """Outcome of wt config validate command."""

    model_config = {"extra": "forbid", "strict": True}

    ok: bool
    config_path: Path | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
