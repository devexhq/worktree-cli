"""Models for catalog scanner and blueprint management."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from worktree.common.models import DefinitionResolutionStatus
from worktree.core.db import CatalogItemType, CatalogRecord


class CatalogResolveStatus(StrEnum):
    """Classified outcomes for Catalog.resolve / resolve_step."""

    OK = "ok"
    NOT_FOUND = "not_found"
    LOAD_ERROR = "load_error"


class CatalogResolveResult(BaseModel):
    """Non-raising result of resolving a catalog YAML document."""

    model_config = {"extra": "forbid", "strict": True}

    status: CatalogResolveStatus
    name: str
    raw: dict[str, Any] | None = None
    record: CatalogRecord | None = None
    matches: list[CatalogRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a catalog document was loaded as a YAML object."""
        return self.status == CatalogResolveStatus.OK


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


class CatalogListResult(BaseModel):
    """Result of listing catalog blueprints and templates."""

    model_config = {"extra": "forbid", "strict": True}

    items: list[CatalogRecord] = Field(default_factory=list)
    type_filter: CatalogItemType | str | None = None
    templates: list[tuple[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if list operation completed without errors."""
        return not self.errors


class CatalogShowResult(BaseModel):
    """Result of showing a catalog blueprint or packaged template."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    content: str | None = None
    template_matches: list[tuple[str, str]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if a blueprint or template was found without errors."""
        return not self.errors and (self.item is not None or self.content is not None or bool(self.template_matches))


class CatalogDeleteResult(BaseModel):
    """Result of deleting a catalog blueprint."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    deleted: bool = False
    cancelled: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if item deletion succeeded."""
        return not self.errors and self.deleted


class CatalogCreateResult(BaseModel):
    """Result of creating a catalog blueprint."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if blueprint creation succeeded."""
        return not self.errors and self.item is not None
