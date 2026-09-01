"""Outcome models for sandbox CLI commands."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from worktree.core.db import SandboxRecord
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxPruneResult,
)


class SandboxListStatus(StrEnum):
    """Classified outcome for ``wt sandbox list``."""

    OK = "ok"
    NOT_INITIALIZED = "not_initialized"


class SandboxListResult(BaseModel):
    """Structured result for ``wt sandbox list`` before rendering."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxListStatus
    sandboxes: list[SandboxRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when listing can proceed (including empty tables)."""
        return self.status == SandboxListStatus.OK and not self.errors


class SandboxShowStatus(StrEnum):
    """Classified outcome for ``wt sandbox show``."""

    OK = "ok"
    NOT_INITIALIZED = "not_initialized"
    NOT_FOUND = "not_found"


class SandboxShowResult(BaseModel):
    """Structured result for ``wt sandbox show`` before rendering."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxShowStatus
    sandbox: SandboxRecord | None = None
    disk_present: bool = False
    reconciled: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when a sandbox row is available to render."""
        return self.status == SandboxShowStatus.OK and self.sandbox is not None and not self.errors


class SandboxDeleteStatus(StrEnum):
    """Classified outcome for ``wt sandbox delete`` before confirmation."""

    READY = "ready"
    ALREADY_CLEANED = "already_cleaned"
    NOT_INITIALIZED = "not_initialized"
    NOT_FOUND = "not_found"


class SandboxDeleteResult(BaseModel):
    """Structured result for ``wt sandbox delete`` before confirm/cleanup."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxDeleteStatus
    sandbox: SandboxRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when delete may proceed (ready) or is an already-cleaned no-op."""
        return (
            self.status
            in {
                SandboxDeleteStatus.READY,
                SandboxDeleteStatus.ALREADY_CLEANED,
            }
            and not self.errors
        )


class SandboxCreateCommandOutcome(BaseModel):
    """Outcome for wt sandbox create command."""

    model_config = {"extra": "forbid", "strict": True}

    session_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox session was created without errors."""
        return not self.errors and self.session_id is not None


class SandboxListCommandOutcome(BaseModel):
    """Outcome for wt sandbox list command."""

    model_config = {"extra": "forbid", "strict": True}

    sandboxes: list[SandboxRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandboxes were listed without errors."""
        return not self.errors


class SandboxShowCommandOutcome(BaseModel):
    """Outcome for wt sandbox show command."""

    model_config = {"extra": "forbid", "strict": True}

    sandbox: SandboxRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox was found without errors."""
        return not self.errors and self.sandbox is not None


class SandboxDeleteCommandOutcome(BaseModel):
    """Outcome for wt sandbox delete command."""

    model_config = {"extra": "forbid", "strict": True}

    deleted: bool = False
    already_cleaned: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox was deleted or already cleaned without errors."""
        return not self.errors and (self.deleted or self.already_cleaned)


class SandboxApplyCommandOutcome(BaseModel):
    """Outcome for wt sandbox apply command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxApplyResult | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox apply completed without errors."""
        return not self.errors and (self.result is not None and self.result.ok)


class SandboxDiffCommandOutcome(BaseModel):
    """Outcome for wt sandbox diff command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxDiffResult | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox diff completed without errors."""
        return not self.errors and (
            self.result is not None and (self.result.ok or self.result.status == SandboxDiffStatus.EMPTY_DIFF)
        )


class SandboxPruneCommandOutcome(BaseModel):
    """Outcome for wt sandbox prune command."""

    model_config = {"extra": "forbid", "strict": True}

    result: SandboxPruneResult | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if sandbox prune completed without errors."""
        return not self.errors and (self.result is not None and self.result.ok)
