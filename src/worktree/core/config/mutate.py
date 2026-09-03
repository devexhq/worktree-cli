"""Dot-path mutation helpers for `.worktree/config.json`."""

from __future__ import annotations

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from worktree.common.filesystem import Filesystem
from worktree.common.models import BaseResult
from worktree.common.schema_validation import CONFIG_VALIDATOR
from worktree.core.config.loader import (
    _map_worktree_config,
    clear_config_cache,
    resolve_config_path,
)


class ConfigSetStatus(StrEnum):
    """Classified outcomes for setting a config value by dot-path."""

    OK = "ok"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    SCHEMA_INVALID = "schema_invalid"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"
    TYPE_COLLISION = "type_collision"
    INVALID_PATH = "invalid_path"
    WRITE_FAILED = "write_failed"


class ConfigSetResult(BaseResult):
    """Non-raising result of a config dot-path set operation."""

    status: ConfigSetStatus
    config_path: Path
    key: str
    value: Any = None

    @property
    def ok(self) -> bool:
        """Return True when the value was written successfully."""
        return self.status == ConfigSetStatus.OK


def set_nested_value(config_dict: dict[str, Any], dot_path: str, value: Any) -> None:
    """Set ``value`` at ``dot_path`` inside ``config_dict`` (in place).

    Intermediate missing segments are created as empty dicts. If an intermediate
    segment exists and is not a dict, raise ``ValueError``.

    Args:
        config_dict: Mutable configuration object root.
        dot_path: Dot-separated key path (e.g. ``agent.model``).
        value: Value to assign at the final segment.

    Raises:
        ValueError: Empty/invalid path or scalar-vs-dict type collision.
    """
    if not dot_path or not dot_path.strip():
        raise ValueError("Cannot set '': config key path must be a non-empty dot path.")

    keys = dot_path.split(".")
    if any(key == "" for key in keys):
        raise ValueError(f"Cannot set '{dot_path}': config key path contains an empty segment.")

    current: dict[str, Any] = config_dict
    for i, key in enumerate(keys[:-1]):
        if key not in current:
            current[key] = {}
        node = current[key]
        if not isinstance(node, dict):
            conflict_path = ".".join(keys[: i + 1])
            raise ValueError(f"Cannot set '{dot_path}'. '{conflict_path}' is already defined as a scalar value.")
        current = node

    current[keys[-1]] = value


def _read_config_object(path: Path, key: str) -> dict[str, Any] | ConfigSetResult:
    """Load ``config.json`` as an object, or return a classified failure."""
    if path.exists() and path.is_dir():
        return ConfigSetResult(
            status=ConfigSetStatus.PATH_IS_DIRECTORY,
            config_path=path,
            key=key,
            errors=[f"Config path is a directory, not a file: '{path}' (CONFIG_PATH_IS_DIRECTORY)."],
            fixes=["Remove the directory or point config_path at a file"],
        )

    if not path.exists():
        return ConfigSetResult(
            status=ConfigSetStatus.NOT_FOUND,
            config_path=path,
            key=key,
            errors=[f"Configuration file not found at '{path}' (CONFIG_NOT_FOUND)."],
            fixes=["Run `wt init` to create `.worktree/config.json`"],
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ConfigSetResult(
            status=ConfigSetStatus.UNREADABLE,
            config_path=path,
            key=key,
            errors=[f"Unable to read config.json at '{path}': {exc} (CONFIG_UNREADABLE)."],
            fixes=["Check file permissions and that the path is readable"],
        )

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        detail = f"line {exc.lineno} column {exc.colno} (char {exc.pos})"
        if exc.msg:
            detail = f"{exc.msg} at {detail}"
        return ConfigSetResult(
            status=ConfigSetStatus.MALFORMED_JSON,
            config_path=path,
            key=key,
            errors=[f"Malformed config.json at '{path}': {detail} (CONFIG_MALFORMED_JSON)."],
            fixes=["Repair JSON syntax, or restore from backup"],
        )

    if not isinstance(data, dict):
        return ConfigSetResult(
            status=ConfigSetStatus.ROOT_NOT_OBJECT,
            config_path=path,
            key=key,
            errors=[f"Malformed config.json at '{path}': root must be an object (CONFIG_ROOT_NOT_OBJECT)."],
            fixes=["Ensure config.json is a JSON object, not an array or scalar"],
        )

    return data


def _validate_mutated_config(
    updated: dict[str, Any],
    path: Path,
    key: str,
) -> ConfigSetResult | None:
    """Return a schema-invalid result, or ``None`` when mapping succeeds."""
    validation = CONFIG_VALIDATOR.validate(updated)
    if not validation.ok:
        return ConfigSetResult(
            status=ConfigSetStatus.SCHEMA_INVALID,
            config_path=path,
            key=key,
            errors=[
                "\n".join(
                    [
                        "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                        *(f"- {msg}" for msg in validation.errors),
                    ]
                )
            ],
            fixes=[
                "Run `wt config validate` for details",
                "Or `wt init --repair` to insert missing keys without overwriting values",
            ],
        )

    try:
        _map_worktree_config(updated)
    except Exception as exc:
        return ConfigSetResult(
            status=ConfigSetStatus.SCHEMA_INVALID,
            config_path=path,
            key=key,
            errors=[
                "\n".join(
                    [
                        "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                        *(f"- {msg}" for msg in [str(exc)]),
                    ]
                )
            ],
            fixes=[
                "Run `wt config validate` for details",
                "Or `wt init --repair` to insert missing keys without overwriting values",
            ],
        )

    return None


def set_config_value_result(
    key: str,
    value: Any,
    *,
    path: Path | None = None,
    config_path: Path | None = None,
) -> ConfigSetResult:
    """Load config JSON, set a dot-path value, and persist on success.

    Does not print or call ``sys.exit``. Enforces schema key allow-lists and V1 schema validation.

    Args:
        key: Dot-path key to set.
        value: Native Python value (or string) to assign.
        path: Repository root used when ``config_path`` is omitted.
        config_path: Explicit config path override.

    Returns:
        Classified ``ConfigSetResult`` with absolute ``config_path``.
    """
    resolved_path = resolve_config_path(path=path, config_path=config_path)
    loaded = _read_config_object(resolved_path, key)
    if isinstance(loaded, ConfigSetResult):
        return loaded

    updated = copy.deepcopy(loaded)
    try:
        set_nested_value(updated, key, value)
    except ValueError as exc:
        message = str(exc)
        status = (
            ConfigSetStatus.TYPE_COLLISION
            if "already defined as a scalar value" in message
            else ConfigSetStatus.INVALID_PATH
        )
        return ConfigSetResult(
            status=status,
            config_path=resolved_path,
            key=key,
            errors=[message],
        )

    schema_error = _validate_mutated_config(updated, resolved_path, key)
    if schema_error is not None:
        return schema_error

    try:
        Filesystem.atomic_write_json(resolved_path, updated)
    except OSError as exc:
        return ConfigSetResult(
            status=ConfigSetStatus.WRITE_FAILED,
            config_path=resolved_path,
            key=key,
            errors=[f"Unable to write config.json at '{resolved_path}': {exc} (CONFIG_WRITE_FAILED)."],
            fixes=["Check file permissions and free disk space"],
        )

    clear_config_cache(resolved_path)
    return ConfigSetResult(
        status=ConfigSetStatus.OK,
        config_path=resolved_path,
        key=key,
        value=value,
        errors=[],
    )
