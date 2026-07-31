"""Load and validate `.worktree/config.json` without side effects."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from getworktree.common.fs import get_worktree_config_file
from getworktree.common.schema_validation import CONFIG_VALIDATOR
from getworktree.core.config.models import WorktreeConfig


class ConfigLoadStatus(StrEnum):
    """Classified outcomes for loading `.worktree/config.json`."""

    OK = "ok"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    SCHEMA_INVALID = "schema_invalid"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"


class ConfigLoadResult(BaseModel):
    """Non-raising result of load + schema validation for config.json."""

    model_config = {"extra": "forbid", "strict": True}

    status: ConfigLoadStatus
    config_path: Path
    raw: dict[str, Any] | None = None
    config: WorktreeConfig | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when config loaded and validated successfully."""
        return self.status == ConfigLoadStatus.OK


def resolve_config_path(
    cwd: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    """Return absolute path to config.json.

    Args:
        cwd: Repository root used when ``config_path`` is omitted.
        config_path: Explicit config path; wins when provided.

    Returns:
        Absolute path to the config file.
    """
    if config_path is not None:
        return config_path.expanduser().resolve()
    root = (cwd or Path.cwd()).expanduser().resolve()
    return get_worktree_config_file(root).resolve()


def _error_not_found(path: Path) -> str:
    return (
        f"Configuration file not found at '{path}' (CONFIG_NOT_FOUND).\n"
        "Fix:\n"
        "- run `wt init` to create `.worktree/config.json`"
    )


def _error_malformed_json(path: Path, detail: str) -> str:
    return (
        f"Malformed config.json at '{path}': {detail} (CONFIG_MALFORMED_JSON).\n"
        "Fix:\n"
        "- repair JSON syntax, or restore from backup"
    )


def _error_root_not_object(path: Path) -> str:
    return (
        f"Malformed config.json at '{path}': root must be an object "
        f"(CONFIG_ROOT_NOT_OBJECT).\n"
        "Fix:\n"
        "- ensure config.json is a JSON object, not an array or scalar"
    )


def _error_schema_invalid(messages: list[str]) -> list[str]:
    lines = ["Config schema validation failed (CONFIG_SCHEMA_INVALID):"]
    lines.extend(f"- {msg}" for msg in messages)
    lines.extend(
        [
            "Fix:",
            "- run `wt config validate` for details",
            "- or `wt init --repair` to insert missing keys without overwriting values",
        ]
    )
    return ["\n".join(lines)]


def _error_path_is_directory(path: Path) -> str:
    return (
        f"Config path is a directory, not a file: '{path}' "
        f"(CONFIG_PATH_IS_DIRECTORY).\n"
        "Fix:\n"
        "- remove the directory or point config_path at a file"
    )


def _error_unreadable(path: Path, detail: str) -> str:
    return (
        f"Unable to read config.json at '{path}': {detail} "
        f"(CONFIG_UNREADABLE).\n"
        "Fix:\n"
        "- check file permissions and that the path is readable"
    )


def load_config_result(
    cwd: Path | None = None,
    *,
    config_path: Path | None = None,
) -> ConfigLoadResult:
    """Load and validate config without raising.

    Primary load surface for commands. Does not print, exit, create, or mutate
    config files.

    Args:
        cwd: Repository root for default path resolution.
        config_path: Explicit path override.

    Returns:
        Classified ``ConfigLoadResult`` with absolute ``config_path``.
    """
    path = resolve_config_path(cwd=cwd, config_path=config_path)

    if path.exists() and path.is_dir():
        return ConfigLoadResult(
            status=ConfigLoadStatus.PATH_IS_DIRECTORY,
            config_path=path,
            errors=[_error_path_is_directory(path)],
        )

    if not path.exists():
        return ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=path,
            errors=[_error_not_found(path)],
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ConfigLoadResult(
            status=ConfigLoadStatus.UNREADABLE,
            config_path=path,
            errors=[_error_unreadable(path, str(exc))],
        )

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        detail = f"line {exc.lineno} column {exc.colno} (char {exc.pos})"
        if exc.msg:
            detail = f"{exc.msg} at {detail}"
        return ConfigLoadResult(
            status=ConfigLoadStatus.MALFORMED_JSON,
            config_path=path,
            errors=[_error_malformed_json(path, detail)],
        )

    if not isinstance(data, dict):
        return ConfigLoadResult(
            status=ConfigLoadStatus.ROOT_NOT_OBJECT,
            config_path=path,
            errors=[_error_root_not_object(path)],
        )

    validation = CONFIG_VALIDATOR.validate(data)
    if not validation.ok:
        return ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=path,
            raw=data,
            errors=_error_schema_invalid(validation.errors),
        )

    try:
        config = _map_worktree_config(data)
    except Exception as exc:  # pydantic ValidationError and similar
        return ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=path,
            raw=data,
            errors=_error_schema_invalid([str(exc)]),
        )

    return ConfigLoadResult(
        status=ConfigLoadStatus.OK,
        config_path=path,
        raw=data,
        config=config,
        errors=[],
    )


def _map_worktree_config(raw: dict[str, Any]) -> WorktreeConfig:
    """Map a schema-valid raw dict into ``WorktreeConfig``."""
    project_raw = raw.get("project") or {}
    project_name = project_raw.get("name") or "unnamed_project"
    normalized = {
        **raw,
        "project": {
            **project_raw,
            "name": str(project_name),
        },
    }
    return WorktreeConfig.model_validate(normalized)


def load_raw_config(config_path: Path) -> dict[str, Any]:
    """Load JSON object or raise with classified message.

    Args:
        config_path: Path to the config file.

    Returns:
        Parsed JSON object.

    Raises:
        FileNotFoundError: When the file is missing.
        ValueError: For other classified load failures.
        OSError: When the path cannot be read.
    """
    result = load_config_result(config_path=config_path)
    if result.status == ConfigLoadStatus.OK:
        assert result.raw is not None
        return result.raw
    if result.status == ConfigLoadStatus.NOT_FOUND:
        raise FileNotFoundError(
            result.errors[0] if result.errors else str(result.status)
        )
    if result.status == ConfigLoadStatus.UNREADABLE:
        raise OSError(result.errors[0] if result.errors else str(result.status))
    raise ValueError(result.errors[0] if result.errors else str(result.status))


def parse_and_validate_config(raw: dict[str, Any]) -> WorktreeConfig:
    """Schema + Pydantic mapping; raise on failure.

    Args:
        raw: Parsed JSON object (must already be a dict).

    Returns:
        Typed ``WorktreeConfig``.

    Raises:
        ValueError: When schema or model validation fails.
    """
    validation = CONFIG_VALIDATOR.validate(raw)
    if not validation.ok:
        raise ValueError(_error_schema_invalid(validation.errors)[0])
    try:
        return _map_worktree_config(raw)
    except Exception as exc:
        raise ValueError(_error_schema_invalid([str(exc)])[0]) from exc


def load_config(
    cwd: Path | None = None,
    *,
    config_path: Path | None = None,
) -> WorktreeConfig:
    """Return WorktreeConfig or raise with classified message.

    Args:
        cwd: Repository root for default path resolution.
        config_path: Explicit path override.

    Returns:
        Typed ``WorktreeConfig``.

    Raises:
        FileNotFoundError: When the config file is missing.
        ValueError: For other classified load failures.
        OSError: When the path cannot be read.
    """
    result = load_config_result(cwd=cwd, config_path=config_path)
    if result.status == ConfigLoadStatus.OK:
        assert result.config is not None
        return result.config
    if result.status == ConfigLoadStatus.NOT_FOUND:
        raise FileNotFoundError(
            result.errors[0] if result.errors else str(result.status)
        )
    if result.status == ConfigLoadStatus.UNREADABLE:
        raise OSError(result.errors[0] if result.errors else str(result.status))
    raise ValueError(result.errors[0] if result.errors else str(result.status))
