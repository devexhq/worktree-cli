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
