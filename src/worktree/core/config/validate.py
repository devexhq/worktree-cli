"""Non-raising config validation engine for structured error/warning lists."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import WorktreeConfig


class ConfigValidationStatus(StrEnum):
    """Classified outcomes for validating `.worktree/config.json`."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"


class ConfigValidationResult(BaseModel):
    """Non-raising result of structural + semantic config validation."""

    model_config = {"extra": "forbid", "strict": True}

    status: ConfigValidationStatus
    config_path: Path
    raw: dict[str, Any] | None = None
    config: WorktreeConfig | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when config is structurally and semantically valid."""
        return self.status == ConfigValidationStatus.VALID


_LOAD_STATUS_TO_VALIDATION: dict[ConfigLoadStatus, ConfigValidationStatus] = {
    ConfigLoadStatus.OK: ConfigValidationStatus.VALID,
    ConfigLoadStatus.NOT_FOUND: ConfigValidationStatus.NOT_FOUND,
    ConfigLoadStatus.MALFORMED_JSON: ConfigValidationStatus.MALFORMED_JSON,
    ConfigLoadStatus.ROOT_NOT_OBJECT: ConfigValidationStatus.ROOT_NOT_OBJECT,
    ConfigLoadStatus.SCHEMA_INVALID: ConfigValidationStatus.INVALID,
    ConfigLoadStatus.PATH_IS_DIRECTORY: ConfigValidationStatus.PATH_IS_DIRECTORY,
    ConfigLoadStatus.UNREADABLE: ConfigValidationStatus.UNREADABLE,
}

_PATH_FIELD_NAMES = (
    "root_dir",
    "sessions_dir",
    "artifacts_dir",
    "db_path",
)


def validate_config_result(
    path: Path | None = None,
    *,
    config_path: Path | None = None,
) -> ConfigValidationResult:
    """Validate config without raising.

    Primary validation surface for ``wt config validate``. Does not print,
    exit, create, or mutate config files.

    Args:
        path: Repository root for default path resolution.
        config_path: Explicit path override.

    Returns:
        Classified ``ConfigValidationResult`` with absolute ``config_path``.
    """
    from worktree.core.config.loader import load_config

    loaded = load_config(path=path or Path("."), config_path=config_path)
    status = _LOAD_STATUS_TO_VALIDATION[loaded.status]

    if loaded.status != ConfigLoadStatus.OK:
        return ConfigValidationResult(
            status=status,
            config_path=loaded.config_path,
            raw=loaded.raw,
            config=None,
            errors=list(loaded.errors),
            warnings=[],
        )

    if loaded.config is None:
        return ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=loaded.config_path,
            raw=loaded.raw,
            config=None,
            errors=[
                f"Configuration loaded from '{loaded.config_path}' but the parsed config is missing "
                f"(CONFIG_INTERNAL_INVARIANT)."
            ],
            warnings=[],
        )

    errors = _semantic_errors(loaded.config)
    warnings = _semantic_warnings(loaded.config)
    if errors:
        return ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=loaded.config_path,
            raw=loaded.raw,
            config=None,
            errors=errors,
            warnings=warnings,
        )

    return ConfigValidationResult(
        status=ConfigValidationStatus.VALID,
        config_path=loaded.config_path,
        raw=loaded.raw,
        config=loaded.config,
        errors=[],
        warnings=warnings,
    )


def _semantic_errors(config: WorktreeConfig) -> list[str]:
    """Return semantic errors in FR-6 rule order."""
    errors: list[str] = []

    for field_name in sorted(_PATH_FIELD_NAMES):
        value = getattr(config.paths, field_name)
        if "\x00" in value or "\n" in value or "\r" in value:
            errors.append(
                f"paths.{field_name} contains invalid control characters "
                f"(CONFIG_SEMANTIC_PATH_INVALID).\n"
                "Fix:\n"
                "- use a plain relative path string without newlines or "
                "NUL bytes"
            )

    return errors


def _semantic_warnings(config: WorktreeConfig) -> list[str]:
    """Return semantic warnings in FR-7 rule order."""
    warnings: list[str] = []

    if config.agent.provider != "local" and config.agent.model is None:
        warnings.append(
            "agent.provider is not 'local' but agent.model is missing "
            "(CONFIG_WARN_AGENT_MODEL_MISSING).\n"
            "Fix:\n"
            "- set agent.model or use provider=local"
        )

    endpoint = config.agent.endpoint
    if endpoint is not None and not _is_absolute_http_url(endpoint):
        warnings.append(
            f"agent.endpoint is not an absolute http(s) URL: '{endpoint}' "
            f"(CONFIG_WARN_AGENT_ENDPOINT).\n"
            "Fix:\n"
            "- set agent.endpoint to an absolute http:// or https:// URL, "
            "or null"
        )

    max_active = config.sandbox.max_active_sandboxes
    if max_active > 10:
        warnings.append(
            f"sandbox.max_active_sandboxes ({max_active}) exceeds 10 "
            f"(CONFIG_WARN_SANDBOX_LIMIT).\n"
            "Fix:\n"
            "- lower sandbox.max_active_sandboxes to 10 or fewer"
        )

    return warnings


def _is_absolute_http_url(value: str) -> bool:
    """Return True when ``value`` is an absolute http:// or https:// URL."""
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
