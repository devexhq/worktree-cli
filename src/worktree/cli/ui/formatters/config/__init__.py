"""Config ComponentFormatters decomposed into single-class modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worktree.cli.ui.formatters.common import DispatcherProtocol
from worktree.core.config.loader import ConfigLoadResult
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.mutate import ConfigSetResult
from worktree.core.config.validate import ConfigValidationResult

from .config_load import ConfigLoadFormatter
from .config_set import ConfigSetFormatter
from .config_show import ConfigShowFormatter
from .config_validate import ConfigValidateFormatter


def register_config_formatters(dispatcher: DispatcherProtocol) -> None:
    """Register all config formatters on the provided dispatcher."""
    dispatcher.register(ConfigLoadResult, ConfigLoadFormatter())
    dispatcher.register(WorktreeConfig, ConfigShowFormatter())
    dispatcher.register(ConfigValidationResult, ConfigValidateFormatter())
    dispatcher.register(ConfigSetResult, ConfigSetFormatter())


__all__ = [
    "ConfigLoadFormatter",
    "ConfigSetFormatter",
    "ConfigShowFormatter",
    "ConfigValidateFormatter",
    "register_config_formatters",
]
