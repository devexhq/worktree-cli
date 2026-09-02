"""Load and validate `.worktree/config.json` without side effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from worktree.common.filesystem import Filesystem
from worktree.common.schema_validation import CONFIG_VALIDATOR
from worktree.core.config.models import WorktreeConfig


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


@dataclass
class _CachedConfig:
    mtime_ns: int
    size: int
    result: ConfigLoadResult


_CONFIG_CACHE: dict[Path, _CachedConfig] = {}


def clear_config_cache(path: Path | None = None) -> None:
    """Explicitly clear in-memory cached configuration."""
    if path is not None:
        target = resolve_config_path(path=path)
        _CONFIG_CACHE.pop(target, None)
    else:
        _CONFIG_CACHE.clear()


def resolve_config_path(
    path: Path | None = None,
    *,
    config_path: Path | None = None,
) -> Path:
    """Return absolute path to config.json.

    Args:
        path: Repository root used when ``config_path`` is omitted.
        config_path: Explicit config path; wins when provided.

    Returns:
        Absolute path to the config file.
    """
    if config_path is not None:
        return config_path.expanduser().resolve()
    return Filesystem(path).config_file


def _read_and_validate_disk_config(target_path: Path) -> ConfigLoadResult:
    """Read, parse, and validate config.json from disk."""
    try:
        text = target_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ConfigLoadResult(
            status=ConfigLoadStatus.UNREADABLE,
            config_path=target_path,
            errors=[
                f"Unable to read config.json at '{target_path}': {exc} (CONFIG_UNREADABLE).\n"
                "Fix:\n"
                "- check file permissions and that the path is readable"
            ],
        )

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        detail = f"line {exc.lineno} column {exc.colno} (char {exc.pos})"
        if exc.msg:
            detail = f"{exc.msg} at {detail}"
        return ConfigLoadResult(
            status=ConfigLoadStatus.MALFORMED_JSON,
            config_path=target_path,
            errors=[
                f"Malformed config.json at '{target_path}': {detail} (CONFIG_MALFORMED_JSON).\n"
                "Fix:\n"
                "- repair JSON syntax, or restore from backup"
            ],
        )

    if not isinstance(data, dict):
        return ConfigLoadResult(
            status=ConfigLoadStatus.ROOT_NOT_OBJECT,
            config_path=target_path,
            errors=[
                f"Malformed config.json at '{target_path}': root must be an object (CONFIG_ROOT_NOT_OBJECT).\n"
                "Fix:\n"
                "- ensure config.json is a JSON object, not an array or scalar"
            ],
        )

    validation = CONFIG_VALIDATOR.validate(data)
    if not validation.ok:
        return ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=target_path,
            raw=data,
            errors=[
                "\n".join(
                    [
                        "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                        *(f"- {msg}" for msg in validation.errors),
                        "Fix:",
                        "- run `wt config validate` for details",
                        "- or `wt init --repair` to insert missing keys without overwriting values",
                    ]
                )
            ],
        )

    try:
        config = _map_worktree_config(data)
    except Exception as exc:  # pydantic ValidationError and similar
        return ConfigLoadResult(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=target_path,
            raw=data,
            errors=[
                "\n".join(
                    [
                        "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                        *(f"- {msg}" for msg in [str(exc)]),
                        "Fix:",
                        "- run `wt config validate` for details",
                        "- or `wt init --repair` to insert missing keys without overwriting values",
                    ]
                )
            ],
        )

    return ConfigLoadResult(
        status=ConfigLoadStatus.OK,
        config_path=target_path,
        raw=data,
        config=config,
        errors=[],
    )


def _check_path_existence(target_path: Path) -> ConfigLoadResult | None:
    """Validate that target_path exists and is a file."""
    if target_path.exists() and target_path.is_dir():
        _CONFIG_CACHE.pop(target_path, None)
        return ConfigLoadResult(
            status=ConfigLoadStatus.PATH_IS_DIRECTORY,
            config_path=target_path,
            errors=[
                f"Config path is a directory, not a file: '{target_path}' (CONFIG_PATH_IS_DIRECTORY).\n"
                "Fix:\n"
                "- remove the directory or point config_path at a file"
            ],
        )

    if not target_path.exists():
        _CONFIG_CACHE.pop(target_path, None)
        return ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=target_path,
            errors=[
                f"Configuration file not found at '{target_path}' (CONFIG_NOT_FOUND).\n"
                "Fix:\n"
                "- run `wt init` to create `.worktree/config.json`"
            ],
        )
    return None


def _get_cached_config(
    target_path: Path,
    stat: Any,
    bypass_cache: bool,
) -> ConfigLoadResult | None:
    """Return cached ConfigLoadResult if stat matches in-memory entry."""
    if bypass_cache or stat is None:
        return None
    cached = _CONFIG_CACHE.get(target_path)
    if cached is not None and cached.mtime_ns == stat.st_mtime_ns and cached.size == stat.st_size:
        return cached.result
    return None


def load_config(
    path: Path | None = None,
    *,
    config_path: Path | None = None,
    bypass_cache: bool = False,
) -> ConfigLoadResult:
    """Load and validate config without raising.

    Primary load surface for commands. Does not print, exit, create, or mutate
    config files. Uses an in-memory cache validated against file modification time.

    Args:
        path: Repository root for default path resolution. Defaults to CWD worktree root.
        config_path: Explicit path override.
        bypass_cache: When True, bypasses the in-memory cache and reads disk directly.

    Returns:
        Classified ``ConfigLoadResult`` with absolute ``config_path``.
    """
    target_path = resolve_config_path(path=path, config_path=config_path)

    path_error = _check_path_existence(target_path)
    if path_error is not None:
        return path_error

    try:
        stat = target_path.stat()
    except OSError:
        stat = None

    cached = _get_cached_config(target_path, stat, bypass_cache)
    if cached is not None:
        return cached

    result = _read_and_validate_disk_config(target_path)
    if stat is not None and result.ok:
        _CONFIG_CACHE[target_path] = _CachedConfig(
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            result=result,
        )
    return result


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
        raise ValueError(
            "\n".join(
                [
                    "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                    *(f"- {msg}" for msg in validation.errors),
                    "Fix:",
                    "- run `wt config validate` for details",
                    "- or `wt init --repair` to insert missing keys without overwriting values",
                ]
            )
        )
    try:
        return _map_worktree_config(raw)
    except Exception as exc:
        raise ValueError(
            "\n".join(
                [
                    "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                    f"- {exc}",
                    "Fix:",
                    "- run `wt config validate` for details",
                    "- or `wt init --repair` to insert missing keys without overwriting values",
                ]
            )
        ) from exc
