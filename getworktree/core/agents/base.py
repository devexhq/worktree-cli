"""Shared agent adapter protocol and request/response DTOs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from getworktree.core.loops.payload import AgentFailurePayload


class AgentResponseStatus(StrEnum):
    """Normalized outcomes from an agent adapter call."""

    PROPOSED_PATCH = "proposed_patch"
    NO_OP = "no_op"
    UNFIXABLE = "unfixable"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


class AgentRequest(BaseModel):
    """Input package for ``AgentAdapter.propose_fix``."""

    model_config = {"extra": "forbid", "strict": True}

    mode: Literal["fix_failure", "review_remediation"]
    payload: AgentFailurePayload
    sandbox_path: Path
    timeout_seconds: int = Field(ge=1)
    model: str | None = None
    endpoint: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_files: int | None = None
    max_patch_kb: int | None = None
    reject_binary_changes: bool | None = None


class AgentResponse(BaseModel):
    """Normalized result of an agent fix proposal."""

    model_config = {"extra": "forbid", "strict": True}

    status: AgentResponseStatus
    unified_diff: str | None = None
    summary: str | None = None
    unfixable_reason: str | None = None
    raw_text: str | None = None
    duration_ms: int = 0
    errors: list[str] = Field(default_factory=list)
    mutation_baseline_ref: str | None = None

    @property
    def ok(self) -> bool:
        """Return True only when a patch was proposed."""
        return self.status == AgentResponseStatus.PROPOSED_PATCH


@runtime_checkable
class AgentAdapter(Protocol):
    """Provider-agnostic contract for requesting a fix from an agent."""

    def propose_fix(self, request: AgentRequest) -> AgentResponse:
        """Propose a fix for the failure described in ``request``."""
        ...
