"""Command outcome models for wt catalog subcommands."""

from __future__ import annotations

from pydantic import BaseModel, Field

from getworktree.core.db import CatalogItemType, CatalogRecord


class CatalogListCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog list``."""

    model_config = {"extra": "forbid", "strict": True}

    items: list[CatalogRecord] = Field(default_factory=list)
    type_filter: CatalogItemType | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if list operation completed without errors."""
        return not self.errors


class CatalogCreateCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog create``."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if item creation succeeded."""
        return not self.errors and self.item is not None


class CatalogShowCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog show``."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    content: str | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if template item was found and rendered."""
        return not self.errors and self.item is not None


class CatalogDeleteCommandOutcome(BaseModel):
    """Outcome of running ``wt catalog delete``."""

    model_config = {"extra": "forbid", "strict": True}

    item: CatalogRecord | None = None
    deleted: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if item deletion succeeded."""
        return not self.errors and self.deleted
