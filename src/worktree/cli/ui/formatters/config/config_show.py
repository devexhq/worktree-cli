"""ComponentFormatter for WorktreeConfig."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.core.config.loader import resolve_config_path
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.serialize import as_json


class ConfigShowFormatter(ComponentFormatter[WorktreeConfig]):
    """Formatter for effective Worktree configuration."""

    def to_rich(self, data: WorktreeConfig) -> Any:
        """Render config source path header and normalized JSON block."""
        config_path = resolve_config_path()
        payload = f"Config: {config_path.as_posix()}\nStatus: valid\n\n{as_json(data)}"
        return Text(payload)

    def to_json_serializable(self, data: WorktreeConfig) -> dict[str, Any]:
        """Convert WorktreeConfig to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
