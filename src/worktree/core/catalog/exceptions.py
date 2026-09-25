"""Exceptions for the catalog inventory facade."""

from __future__ import annotations

from worktree.common.exceptions import DefinitionError


class CatalogError(DefinitionError):
    """Base catalog facade error."""


class CatalogFileNotFoundError(CatalogError):
    """Raised by Catalog.read_yaml when the path does not exist."""


class CatalogYamlError(CatalogError):
    """Raised by Catalog.read_yaml when YAML is unreadable or not an object."""


class CatalogWriteError(CatalogError):
    """Raised by Catalog.save when the atomic write fails."""


class CatalogProtectionError(CatalogError):
    """Raised when attempting to delete or mutate a protected bundled catalog template."""


class CatalogTierDeleteError(CatalogError):
    """Raised when attempting to delete a catalog item resolved from a non-REPO tier."""
