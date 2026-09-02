"""Config domain facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worktree.core.config.exceptions import ConfigLoadError
from worktree.core.config.generator import ConfigGenerationResult
from worktree.core.config.loader import (
    ConfigLoadResult,
)
from worktree.core.config.models import (
    AgentConfig,
    ConcurrencyConfig,
    DoctorConfig,
    HistoryConfig,
    PathsConfig,
    ProjectConfig,
    PruneConfig,
    SandboxConfig,
    TelemetryConfig,
    WorktreeConfig,
)
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
        self._cached_config: WorktreeConfig | None = None

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

    # ------------------------------------------------------------------ #
    # Accessor properties (load-once, raise on failure)                  #
    # ------------------------------------------------------------------ #

    @property
    def _loaded_config(self) -> WorktreeConfig:
        """Load and cache the WorktreeConfig, raising ConfigLoadError on failure."""
        if self._cached_config is None:
            result = self.load()
            if not result.ok or result.config is None:
                errors = "; ".join(result.errors) if result.errors else "unknown error"
                raise ConfigLoadError(f"Failed to load config at '{self.path}': {errors}")
            self._cached_config = result.config
        return self._cached_config

    @property
    def version(self) -> int:
        """Return the config schema version."""
        return self._loaded_config.version

    @property
    def project(self) -> ProjectConfig:
        """Return the project identity section of the loaded config."""
        return self._loaded_config.project

    @property
    def paths(self) -> PathsConfig:
        """Return the filesystem paths section of the loaded config."""
        return self._loaded_config.paths

    @property
    def agent(self) -> AgentConfig:
        """Return the agent provider section of the loaded config."""
        return self._loaded_config.agent

    @property
    def sandbox(self) -> SandboxConfig:
        """Return the sandbox lifecycle section of the loaded config."""
        return self._loaded_config.sandbox

    @property
    def history(self) -> HistoryConfig:
        """Return the session history retention section of the loaded config."""
        return self._loaded_config.history

    @property
    def doctor(self) -> DoctorConfig:
        """Return the doctor check toggles section of the loaded config."""
        return self._loaded_config.doctor

    @property
    def prune(self) -> PruneConfig:
        """Return the prune cleanup toggles section of the loaded config."""
        return self._loaded_config.prune

    @property
    def telemetry(self) -> TelemetryConfig:
        """Return the optional telemetry section of the loaded config."""
        return self._loaded_config.telemetry

    @property
    def concurrency(self) -> ConcurrencyConfig:
        """Return the concurrency and locking section of the loaded config."""
        return self._loaded_config.concurrency

    # ------------------------------------------------------------------ #
    # Static and class-method helpers                                     #
    # ------------------------------------------------------------------ #

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
