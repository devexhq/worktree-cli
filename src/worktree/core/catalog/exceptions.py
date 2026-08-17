"""Exceptions for the catalog inventory facade."""

from __future__ import annotations


class CatalogError(Exception):
    """Base catalog facade error."""


class CatalogFileNotFoundError(CatalogError):
    """Raised by Catalog.read_yaml when the path does not exist."""


class CatalogYamlError(CatalogError):
    """Raised by Catalog.read_yaml when YAML is unreadable or not an object."""


class CatalogWriteError(CatalogError):
    """Raised by Catalog.save when the atomic write fails."""
