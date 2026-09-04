"""Catalog ComponentFormatters decomposed into single-class modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
)

from .catalog_create import CatalogCreateFormatter
from .catalog_delete import CatalogDeleteFormatter
from .catalog_list import CatalogListFormatter
from .catalog_show import CatalogShowFormatter


def register_catalog_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all catalog formatters on the provided dispatcher."""
    dispatcher.register(CatalogListResult, CatalogListFormatter())
    dispatcher.register(CatalogShowResult, CatalogShowFormatter())
    dispatcher.register(CatalogDeleteResult, CatalogDeleteFormatter())
    dispatcher.register(CatalogCreateResult, CatalogCreateFormatter())


__all__ = [
    "CatalogCreateFormatter",
    "CatalogDeleteFormatter",
    "CatalogListFormatter",
    "CatalogShowFormatter",
    "register_catalog_formatters",
]
