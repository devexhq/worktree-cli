"""Config domain facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worktree.core.config.generator import ConfigGenerationResult
from worktree.core.config.loader import (
    ConfigLoadResult,
)
from worktree.core.config.models import WorktreeConfig
from worktree.core.config.mutate import (
    ConfigSetResult,
)
from worktree.core.config.parser import parse_config_value
from worktree.core.config.serialize import as_json, serialize_config
from worktree.core.config.validate import (
    ConfigValidationResult,
)


class Config:
    """Unified entrypoint for workspace configuration loading, validation, mutation, and serialization."""

    def __init__(self, path: Path = Path(".")) -> None:
        self.path = path.resolve()
        self.cwd = self.path

    def load(self, *, config_path: Path | None = None) -> ConfigLoadResult:
        """Load and parse ``config.json`` returning a structured result."""
        from worktree.core.config.loader import load_config

        return load_config(path=self.path, config_path=config_path)

    def validate(self, *, config_path: Path | None = None) -> ConfigValidationResult:
        """Validate ``config.json`` against schema constraints and return structured report."""
        from worktree.core.config.validate import validate_config_result

        return validate_config_result(path=self.path, config_path=config_path)

    def set(self, key: str, value: Any) -> ConfigSetResult:
        """Set a dot-path configuration key and persist to disk."""
        from worktree.core.config.mutate import set_config_value_result

        parsed_value = self.parse_value(value) if isinstance(value, str) else value
        return set_config_value_result(key, parsed_value, path=self.path)

    def generate(
        self,
        *,
        overwrite: bool = False,
        repair: bool = False,
        project_name: str | None = None,
    ) -> ConfigGenerationResult:
        """Generate a default ``config.json`` file in workspace."""
        from worktree.core.config.generator import generate_default_config

        p_name = project_name or self.path.name
        cfg_path = (self.path / ".worktree" / "config.json").resolve()
        return generate_default_config(cfg_path, p_name, overwrite=overwrite, repair=repair)

    @staticmethod
    def parse_value(value: str) -> Any:
        """Parse string CLI token into typed Python object (bool, int, float, list, dict, str)."""
        return parse_config_value(value)

    @staticmethod
    def dump(config: WorktreeConfig) -> str:
        """Serialize WorktreeConfig instance into formatted JSON string."""
        return as_json(config)

    @staticmethod
    def serialize(config: WorktreeConfig) -> dict[str, Any]:
        """Serialize WorktreeConfig instance into JSON-ready dictionary."""
        return serialize_config(config)

    @classmethod
    def load_from(cls, path: Path, *, config_path: Path | None = None) -> ConfigLoadResult:
        """Helper to load config at specified path."""
        return cls(path).load(config_path=config_path)

    @classmethod
    def validate_at(cls, path: Path, *, config_path: Path | None = None) -> ConfigValidationResult:
        """Helper to validate config at specified path."""
        return cls(path).validate(config_path=config_path)

    @classmethod
    def set_value(cls, path: Path, key: str, value: Any) -> ConfigSetResult:
        """Helper to set config value at specified path."""
        return cls(path).set(key, value)
