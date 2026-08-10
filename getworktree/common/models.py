from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class YamlFile(BaseModel):
    """Representation of a yaml file from a directory scan."""

    path: Path
    name: str
    content: str | None = ""
    parsed: Any | None = None
    error: str | None = None


class FailurePolicy(StrEnum):
    """Canonical failure-handling vocabulary shared by steps and loop blocks."""

    ABORT = "abort"
    CONTINUE = "continue"
    PROMPT_USER = "prompt_user"
    RETRY = "retry"

    @classmethod
    def context(cls, name: str) -> frozenset["FailurePolicy"]:
        """Return the allowed FailurePolicy subset for a given usage context."""
        if name == "terminal":
            return frozenset({cls.ABORT, cls.CONTINUE, cls.PROMPT_USER})
        return frozenset(cls)


class FailureSpec(BaseModel):
    """Normalized on_failure directive: action, retry tuning, and post-retry escalation."""

    model_config = {"extra": "forbid"}

    action: FailurePolicy
    max_retries: int = Field(default=3, ge=1)
    backoff_ms: int = Field(default=0, ge=0)
    on_max_retries: FailurePolicy = FailurePolicy.ABORT

    @field_validator("action", "on_max_retries", mode="before")
    @classmethod
    def parse_policy(cls, val: Any) -> Any:
        """Coerce string values to FailurePolicy enum instances."""
        if isinstance(val, str):
            try:
                return FailurePolicy(val)
            except ValueError:
                pass
        return val

    @model_validator(mode="after")
    def validate_on_max_retries_context(self) -> "FailureSpec":
        """on_max_retries must be terminal (no RETRY-on-RETRY-exhaustion)."""
        allowed = FailurePolicy.context("terminal")
        if self.on_max_retries not in allowed:
            raise ValueError(f"on_max_retries must be one of {sorted(allowed)}, got {self.on_max_retries!r}.")
        return self
