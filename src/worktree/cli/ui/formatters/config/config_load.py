"""ComponentFormatter for ConfigLoadResult."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.core.config.loader import ConfigLoadResult
from worktree.core.config.serialize import as_json


class ConfigLoadFormatter(ComponentFormatter[ConfigLoadResult]):
    """Formatter for configuration load and validation results."""

    def to_rich(self, data: ConfigLoadResult) -> Any:
        """Render configuration source path header and normalized JSON body, or error panel."""
        if data.ok and data.config is not None:
            payload = f"Config: {data.config_path.as_posix()}\nStatus: valid\n\n{as_json(data.config)}"
            return Text(payload)

        parts: list[str] = []
        if data.errors:
            parts.append("\n\n".join(data.errors))
        else:
            parts.append(f"Configuration failed to load ({data.status.value.upper()}).")
        if data.fixes:
            parts.append("Fix:\n" + "\n".join(f"- {fix}" for fix in data.fixes))
        message = "\n".join(parts)
        return Panel(message, title="Config Error", border_style="red")

    def to_json_serializable(self, data: ConfigLoadResult) -> dict[str, Any]:
        """Convert ConfigLoadResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
