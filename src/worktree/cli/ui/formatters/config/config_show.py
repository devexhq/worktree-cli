"""ComponentFormatter for WorktreeConfig."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.config.config_views import ConfigShowView
from worktree.common.types import ComponentFormatter
from worktree.core.config.loader import resolve_config_path
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.serialize import as_json


class ConfigShowFormatter(ComponentFormatter[WorktreeConfig, ConfigShowView]):
    """Formatter for effective Worktree configuration."""

    def transform(self, data: WorktreeConfig) -> ConfigShowView:
        """Derive the presentation-ready view from WorktreeConfig.

        Args:
            data: Domain WorktreeConfig object.

        Returns:
            ConfigShowView containing resolved path, validity status, and nested config.
        """
        config_path = resolve_config_path()
        return ConfigShowView(
            config_path=config_path,
            status="valid",
            config=data,
        )

    def to_rich(self, data: WorktreeConfig) -> Any:
        """Render config source path header and normalized JSON block."""
        view = self.transform(data)
        payload = f"Config: {view.config_path.as_posix()}\nStatus: {view.status}\n\n{as_json(view.config)}"
        return Text(payload)
