"""Models for catalog scanner and blueprint management."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from getworktree.common.models import DefinitionResolutionStatus
from getworktree.core.db import CatalogItemType, CatalogRecord


class CatalogScanResult(BaseModel):
    """Result of scanning and indexing catalog blueprint directories."""

    model_config = {"extra": "forbid", "strict": True}

    items: list[CatalogRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when scanning and DB indexing completed without errors."""
        return not self.errors


class CatalogSubdirectoryScanResult(BaseModel):
    """Result of scanning a catalog subdirectory."""

    model_config = {"extra": "forbid", "strict": True}

    scanned_records: list[CatalogRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    scanned_shas: set[str] = Field(default_factory=set)


class YamlParseOutcome(BaseModel):
    """Outcome of reading and parsing a YAML catalog blueprint file."""

    model_config = {"extra": "forbid", "strict": True}

    parsed_data: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class DefinitionValidationOutcome(BaseModel):
    """Outcome of validating a catalog blueprint definition against schema and model."""

    model_config = {"extra": "forbid", "strict": True}

    definition: Any | None = None
    status: DefinitionResolutionStatus = DefinitionResolutionStatus.OK
    errors: list[str] = Field(default_factory=list)


__all__ = [
    "CatalogItemType",
    "CatalogRecord",
    "CatalogScanResult",
    "CatalogSubdirectoryScanResult",
    "DefinitionValidationOutcome",
    "YamlParseOutcome",
]
