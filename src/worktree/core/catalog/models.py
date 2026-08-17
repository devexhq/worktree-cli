"""Models for catalog scanner and blueprint management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from worktree.common.models import DefinitionResolutionStatus
from worktree.core.db import CatalogRecord


class SeedResult(BaseModel):
    """Outcome of seeding packaged catalog blueprint templates."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    created_files: list[Path] = Field(default_factory=list)
    skipped_existing_files: list[Path] = Field(default_factory=list)
    overwritten_files: list[Path] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when seeding completed without blocking errors."""
        return not self.errors


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
