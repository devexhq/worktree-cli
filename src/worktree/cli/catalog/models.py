"""Command outcome models for wt catalog subcommands."""

from __future__ import annotations

from pydantic import BaseModel, Field

from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
)
from worktree.core.db import CatalogItemType, CatalogRecord

__all__ = [
    "CatalogCreateCommandOutcome",
    "CatalogDeleteCommandOutcome",
    "CatalogListCommandOutcome",
    "CatalogShowCommandOutcome",
]


class CatalogListCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog list``."""

    model_config = {"extra": "forbid", "strict": True}

    result: CatalogListResult | None = None
    items: list[CatalogRecord] = Field(default_factory=list)
    type_filter: CatalogItemType | str | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if list operation completed without errors."""
        return not self.errors


class CatalogCreateCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog create``."""

    model_config = {"extra": "forbid", "strict": True}

    result: CatalogCreateResult | None = None
    item: CatalogRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if item creation succeeded."""
        return not self.errors and (self.item is not None or (self.result is not None and self.result.ok))


class CatalogShowCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog show``."""

    model_config = {"extra": "forbid", "strict": True}

    result: CatalogShowResult | None = None
    item: CatalogRecord | None = None
    content: str | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if a catalog item or packaged template was found and rendered."""
        return not self.errors and (
            self.item is not None or self.content is not None or (self.result is not None and self.result.ok)
        )


class CatalogDeleteCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog delete``."""

    model_config = {"extra": "forbid", "strict": True}

    result: CatalogDeleteResult | None = None
    item: CatalogRecord | None = None
    deleted: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if item deletion succeeded."""
        return not self.errors and (self.deleted or (self.result is not None and self.result.ok))
