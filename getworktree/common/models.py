from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class YamlFile(BaseModel):
    """Representation of a yaml file from a directory scan."""

    path: Path
    name: str
    content: str | None = ""
    parsed: Any | None = None
    error: str | None = None


class DefinitionResolutionStatus(StrEnum):
    """Classified outcomes for resolving a domain definition by name."""

    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID_NAME = "invalid_name"
    LOAD_ERROR = "load_error"
    DISCOVERY_FAILED = "discovery_failed"


class DefinitionResolutionResult[T](BaseModel):
    """Non-raising result of resolving one domain definition name."""

    model_config = {"extra": "forbid", "strict": True}

    status: DefinitionResolutionStatus
    requested_name: str
    resolved: T | None = None
    definition: Any | None = None
    matches: list[T] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a unique or deterministically chosen entry was found."""
        return self.status == DefinitionResolutionStatus.OK
