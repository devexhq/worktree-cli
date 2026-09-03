"""Unified UI formatters package registering all component formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.catalog import (
    CatalogCreateFormatter,
    CatalogDeleteFormatter,
    CatalogListFormatter,
    CatalogShowFormatter,
    register_catalog_formatters,
)
from worktree.cli.ui.formatters.common import (
    DispatcherProtocol,
    build_error_panel,
    render_list_errors,
    render_list_fixes,
)
from worktree.cli.ui.formatters.config import (
    ConfigLoadFormatter,
    ConfigSetFormatter,
    ConfigShowFormatter,
    ConfigValidateFormatter,
    register_config_formatters,
)
from worktree.cli.ui.formatters.diff import (
    DiffResultFormatter,
    register_diff_formatters,
)
from worktree.cli.ui.formatters.events import (
    ErrorPanelFormatter,
    LoopLifecycleFormatter,
    MessageFormatter,
    RunSuccessFormatter,
    SandboxLifecycleFormatter,
    StepDoneFormatter,
    StepOutputFormatter,
    StepStartFormatter,
    WarningFormatter,
    register_event_formatters,
)
from worktree.cli.ui.formatters.global_cli import (
    WelcomeBannerFormatter,
    register_global_formatters,
)
from worktree.cli.ui.formatters.history import (
    HistoryListFormatter,
    HistoryShowFormatter,
    register_history_formatters,
)
from worktree.cli.ui.formatters.init import (
    InitOutcomeFormatter,
    WorkspaceInitFormatter,
    register_init_formatters,
)
from worktree.cli.ui.formatters.sandbox import (
    PrunedItemFormatter,
    SandboxApplyFormatter,
    SandboxCreateFormatter,
    SandboxDeleteFormatter,
    SandboxDiffFormatter,
    SandboxListFormatter,
    SandboxPruneFormatter,
    SandboxShowFormatter,
    register_sandbox_formatters,
)
from worktree.cli.ui.formatters.status import (
    WorktreeStatusFormatter,
    register_status_formatters,
)

# Alias for backwards compatibility with tests and callers from PR #451
register_ui_formatters = register_event_formatters


def register_all_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all formatters across all domains and events into the dispatcher."""
    register_event_formatters(dispatcher)
    register_catalog_formatters(dispatcher)
    register_config_formatters(dispatcher)
    register_diff_formatters(dispatcher)
    register_history_formatters(dispatcher)
    register_init_formatters(dispatcher)
    register_sandbox_formatters(dispatcher)
    register_status_formatters(dispatcher)
    register_global_formatters(dispatcher)


__all__ = [
    "CatalogCreateFormatter",
    "CatalogDeleteFormatter",
    "CatalogListFormatter",
    "CatalogShowFormatter",
    "ConfigLoadFormatter",
    "ConfigSetFormatter",
    "ConfigShowFormatter",
    "ConfigValidateFormatter",
    "DiffResultFormatter",
    "ErrorPanelFormatter",
    "HistoryListFormatter",
    "HistoryShowFormatter",
    "InitOutcomeFormatter",
    "LoopLifecycleFormatter",
    "MessageFormatter",
    "PrunedItemFormatter",
    "RunSuccessFormatter",
    "SandboxApplyFormatter",
    "SandboxCreateFormatter",
    "SandboxDeleteFormatter",
    "SandboxDiffFormatter",
    "SandboxLifecycleFormatter",
    "SandboxListFormatter",
    "SandboxPruneFormatter",
    "SandboxShowFormatter",
    "StepDoneFormatter",
    "StepOutputFormatter",
    "StepStartFormatter",
    "WarningFormatter",
    "WelcomeBannerFormatter",
    "WorkspaceInitFormatter",
    "WorktreeStatusFormatter",
    "build_error_panel",
    "register_all_formatters",
    "register_catalog_formatters",
    "register_config_formatters",
    "register_diff_formatters",
    "register_event_formatters",
    "register_global_formatters",
    "register_history_formatters",
    "register_init_formatters",
    "register_sandbox_formatters",
    "register_status_formatters",
    "register_ui_formatters",
    "render_list_errors",
    "render_list_fixes",
]
