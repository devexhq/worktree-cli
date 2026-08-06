"""Models for catalog scanner and blueprint management."""

from __future__ import annotations

from pydantic import BaseModel, Field

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


__all__ = ["CatalogItemType", "CatalogRecord", "CatalogScanResult"]
