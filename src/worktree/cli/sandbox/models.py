"""Outcome models for sandbox CLI commands."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.db import SandboxRecord
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxDeleteResult,
    SandboxDeleteStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxPruneResult,
)

__all__ = [
    "SandboxApplyCommandOutcome",
    "SandboxCreateCommandOutcome",
    "SandboxDeleteCommandOutcome",
    "SandboxDeleteResult",
    "SandboxDeleteStatus",
    "SandboxDiffCommandOutcome",
    "SandboxListCommandOutcome",
    "SandboxPruneCommandOutcome",
    "SandboxShowCommandOutcome",
]


class SandboxCreateCommandOutcome(BaseModel):
    """Outcome for wt sandbox create command."""

    model_config = {"extra": "forbid", "strict": True}

    session_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when creation succeeded."""
        return self.session_id is not None and not self.errors


class SandboxDeleteCommandOutcome(BaseModel):
    """Outcome for wt sandbox delete command."""

    model_config = {"extra": "forbid", "strict": True}

    deleted: bool = False
    already_cleaned: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when delete succeeded or was an idempotent no-op."""
        return (self.deleted or self.already_cleaned) and not self.errors


class SandboxApplyCommandOutcome(BaseModel):
    """Outcome for wt sandbox apply command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxApplyResult | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when patch application succeeded."""
        return self.result is not None and self.result.ok and not self.errors


class SandboxDiffCommandOutcome(BaseModel):
    """Outcome for wt sandbox diff command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxDiffResult | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when diff inspection succeeded."""
        return self.result is not None and self.result.status == SandboxDiffStatus.OK and not self.errors


class SandboxListCommandOutcome(BaseModel):
    """Outcome for wt sandbox list command."""

    model_config = {"extra": "forbid", "strict": True}

    sandboxes: list[SandboxRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when listing succeeded."""
        return not self.errors


class SandboxShowCommandOutcome(BaseModel):
    """Outcome for wt sandbox show command."""

    model_config = {"extra": "forbid", "strict": True}

    sandbox: SandboxRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when a sandbox row was found."""
        return self.sandbox is not None and not self.errors


class SandboxPruneCommandOutcome(BaseModel):
    """Outcome for wt sandbox prune command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxPruneResult | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when pruning completed without errors."""
        return self.result is not None and self.result.ok and not self.errors
