"""Outcome models for sandbox CLI commands."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from getworktree.core.db import SandboxRecord


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
