"""Shared non-UI utilities for paths and formatting values."""

import json
from pathlib import Path


def display_path(path: Path, cwd: Path | None = None) -> str:
    """Display a path, preferring POSIX-style relative segments when possible."""
    if cwd:
        try:
            return path.relative_to(cwd).as_posix()
        except ValueError:
            return str(path)

    try:
        return path.as_posix()
    except Exception:
        # Intentional fallback for path types that don't support as_posix();
        # display_path has no error-reporting channel.
        return str(path)


def resolve_path_from_config(config_file: Path, path_key: str, default: str | Path) -> Path:
    """Resolve a path from a config file.

    If the config file does not exist, return the default path.
    If the path key is not in the config file, return the default path.
    """
    if not config_file.is_file():
        return Path(default)
    with open(config_file, encoding="utf-8") as f:
        raw = json.load(f)
    paths = raw.get("paths")
    if isinstance(paths, dict) and paths.get(path_key):
        return Path(paths[path_key])
    return Path(default)


def enum_value(value: object) -> str:
    """Return `value.value` when present (enum-like), else `str(value)`."""
    attr = getattr(value, "value", None)
    return attr if isinstance(attr, str) else str(value)
