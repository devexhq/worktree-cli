"""Structured agent failure payload models shared by agent adapters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OmissionReason = Literal[
    "missing",
    "outside_sandbox",
    "directory",
    "binary",
    "max_files",
    "max_file_bytes",
]


class PayloadOmission(BaseModel):
    """Record of a candidate path that was not included in the payload."""

    model_config = {"extra": "forbid", "strict": True}

    path: str
    reason: OmissionReason


class PayloadFile(BaseModel):
    """Sandbox-relative source file content attached to a failure payload."""

    model_config = {"extra": "forbid", "strict": True}

    path: str
    content: str
    truncated: bool = False


class AgentFailurePayload(BaseModel):
    """Bounded context package for an agent fix request."""

    model_config = {"extra": "forbid", "strict": True}

    command: str
    args: list[str]
    trigger_status: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    changed_files: list[str] = Field(default_factory=list)
    files: list[PayloadFile] = Field(default_factory=list)
    omissions: list[PayloadOmission] = Field(default_factory=list)
