"""Filesystem bootstrap for the local Worktree home directory (`.worktree/`).

Symlink policy: the `.worktree` root may be a symlink to a directory; required
subdirectories must be real directories (not symlinks).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from getworktree.common.constants import (
    BOOTSTRAP_META_REL,
    BOOTSTRAP_SCHEMA_VERSION,
    REQUIRED_SUBDIRS,
)
from getworktree.common.utils import display_path
from getworktree.core.loops.seeder import LoopSeedResult


class DirEnsureOutcome(Enum):
    """Result of attempting to ensure a directory exists."""

    CREATED = "created"
    EXISTING = "existing"


@dataclass
class BootstrapResult:
    """Outcome of bootstrapping the `.worktree/` directory tree."""

    root_path: Path
    root_created: bool = False
    dirs_created: list[Path] = field(default_factory=list)
    dirs_existing: list[Path] = field(default_factory=list)
    repaired: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    loop_seed_result: LoopSeedResult = field(default_factory=LoopSeedResult)

    @property
    def ok(self) -> bool:
        """True when bootstrap completed without errors."""
        return not self.errors


def ensure_dir(path: Path, *, allow_symlink: bool = False) -> DirEnsureOutcome:
    """Create a directory if missing.

    Raises ValueError with an actionable message when the path is invalid.
    """
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(
                f"Could not create {display_path(path)}: {exc}. "
                "Check directory permissions and try again."
            ) from exc
        return DirEnsureOutcome.CREATED

    if path.is_symlink():
        if allow_symlink:
            if not path.is_dir():
                raise ValueError(
                    f"{display_path(path)} is a symlink that does not resolve to a directory."
                )
            return DirEnsureOutcome.EXISTING
        raise ValueError(f"{display_path(path)} must be a directory, not a symlink.")
    if path.is_file():
        raise ValueError(f"{display_path(path)} exists but is a file, not a directory.")
    if not path.is_dir():
        raise ValueError(f"{display_path(path)} is not a usable directory.")
    return DirEnsureOutcome.EXISTING


def assert_writable(path: Path) -> None:
    """Verify that an existing path is writable."""
    if not path.exists():
        raise ValueError(f"{display_path(path)} does not exist.")
    if not os.access(path, os.W_OK):
        raise ValueError(
            f"{display_path(path)} is not writable. "
            "Check directory permissions and try again."
        )


def load_existing_bootstrap_metadata(meta_path: Path) -> dict | None:
    """Load `.meta/bootstrap.json` if present and valid."""
    if not meta_path.is_file():
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_bootstrap_metadata(
    meta_path: Path,
    *,
    root_path: Path,
    status: str,
    tool_version: str | None,
    initialized_at: str | None,
) -> None:
    """Write bootstrap metadata for diagnostics and idempotent init."""
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "schema_version": BOOTSTRAP_SCHEMA_VERSION,
        "initialized_at": initialized_at or now,
        "last_checked_at": now,
        "tool_version": tool_version,
        "status": status,
        "root_path": str(root_path),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def bootstrap_worktree(
    root_path: Path,
    *,
    tool_version: str | None = None,
) -> BootstrapResult:
    """Create and validate the Worktree home layout under ``root_path`` (typically ``.worktree``).

    Idempotent: safe to run multiple times; never deletes user data.
    """
    root_path = root_path.resolve()
    result = BootstrapResult(root_path=root_path)
    meta_path = root_path / BOOTSTRAP_META_REL
    loops_path = root_path / "loops"
    prior_meta = load_existing_bootstrap_metadata(meta_path)

    try:
        root_outcome = _ensure_worktree_root(root_path)
        result.root_created = root_outcome == DirEnsureOutcome.CREATED
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    if not result.root_created:
        try:
            assert_writable(root_path)
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

    for name in REQUIRED_SUBDIRS:
        sub_path = root_path / name
        try:
            outcome = ensure_dir(sub_path, allow_symlink=False)
        except ValueError as exc:
            result.errors.append(str(exc))
            return result
        if outcome == DirEnsureOutcome.CREATED:
            result.dirs_created.append(sub_path)
        else:
            result.dirs_existing.append(sub_path)

    try:
        assert_writable(root_path)
        for sub_path in result.dirs_created + result.dirs_existing:
            assert_writable(sub_path)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.repaired = bool(result.dirs_created) and (
        bool(result.dirs_existing) or not result.root_created or prior_meta is not None
    )

    if result.errors:
        return result

    if result.repaired:
        status = "repaired"
    elif result.root_created or result.dirs_created:
        status = "initialized"
    else:
        status = (
            str(prior_meta.get("status", "initialized"))
            if prior_meta
            else "initialized"
        )

    initialized_at: str | None = None
    if prior_meta and prior_meta.get("initialized_at"):
        initialized_at = str(prior_meta["initialized_at"])

    try:
        write_bootstrap_metadata(
            meta_path,
            root_path=root_path,
            status=status,
            tool_version=tool_version,
            initialized_at=initialized_at,
        )
    except OSError as exc:
        result.errors.append(
            f"Could not write bootstrap metadata at {display_path(meta_path)}: {exc}"
        )

    result.loop_seed_result = LoopSeedResult()
    return result


def _ensure_worktree_root(root_path: Path) -> DirEnsureOutcome:
    return ensure_dir(root_path, allow_symlink=True)
