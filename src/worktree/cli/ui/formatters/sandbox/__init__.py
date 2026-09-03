"""Sandbox ComponentFormatters decomposed into single-class modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.sandbox.models import (
    PrunedItem,
    SandboxApplyResult,
    SandboxCreateResult,
    SandboxDeleteResult,
    SandboxDiffResult,
    SandboxListResult,
    SandboxPruneResult,
    SandboxShowResult,
)

from .pruned_item import PrunedItemFormatter
from .sandbox_apply import SandboxApplyFormatter
from .sandbox_create import SandboxCreateFormatter
from .sandbox_delete import SandboxDeleteFormatter
from .sandbox_diff import SandboxDiffFormatter
from .sandbox_list import SandboxListFormatter
from .sandbox_prune import SandboxPruneFormatter
from .sandbox_show import SandboxShowFormatter


def register_sandbox_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all sandbox formatters on the provided dispatcher."""
    dispatcher.register(PrunedItem, PrunedItemFormatter())
    dispatcher.register(SandboxPruneResult, SandboxPruneFormatter())
    dispatcher.register(SandboxShowResult, SandboxShowFormatter())
    dispatcher.register(SandboxListResult, SandboxListFormatter())
    dispatcher.register(SandboxCreateResult, SandboxCreateFormatter())
    dispatcher.register(SandboxApplyResult, SandboxApplyFormatter())
    dispatcher.register(SandboxDeleteResult, SandboxDeleteFormatter())
    dispatcher.register(SandboxDiffResult, SandboxDiffFormatter())


__all__ = [
    "PrunedItemFormatter",
    "SandboxApplyFormatter",
    "SandboxCreateFormatter",
    "SandboxDeleteFormatter",
    "SandboxDiffFormatter",
    "SandboxListFormatter",
    "SandboxPruneFormatter",
    "SandboxShowFormatter",
    "register_sandbox_formatters",
]
