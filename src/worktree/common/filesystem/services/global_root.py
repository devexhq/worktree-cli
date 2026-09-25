"""Resolve and provision the global Worktree filesystem hierarchy."""

from __future__ import annotations

import os
from pathlib import Path

from worktree.common.filesystem.exceptions import InvalidGlobalRootError
from worktree.common.filesystem.models import GlobalPaths


def resolve_global_paths(override_root: Path | None = None) -> GlobalPaths:
    """Resolve the canonical global Worktree hierarchy without creating it."""
    if override_root is not None:
        source_root = override_root
    elif "WORKTREE_HOME" in os.environ:
        source_root = Path(os.environ["WORKTREE_HOME"])
    else:
        source_root = Path.home() / ".worktree"

    return GlobalPaths.from_root(source_root)


def ensure_global_layout(override_root: Path | None = None, *, ignore_global_root_error: bool = False) -> GlobalPaths:
    """Create the global Worktree directory layout and return its canonical paths."""
    paths = resolve_global_paths(override_root)
    if paths.root.joinpath(".git").is_dir() and not ignore_global_root_error:
        raise InvalidGlobalRootError(
            f"Global Worktree root '{paths.root}' must not be a Git repository; "
            "remove its .git directory or choose a different WORKTREE_HOME."
        )

    layout_directories = (
        paths.root,
        paths.global_dir,
        paths.global_catalog_dir,
        paths.global_catalog_dir / "blueprints",
        paths.global_catalog_dir / "steps",
        paths.user_dir,
        paths.user_catalog_dir,
        paths.user_catalog_dir / "blueprints",
        paths.user_catalog_dir / "steps",
        paths.data_dir,
        paths.storage_dir,
        paths.storage_dir / "projects",
    )
    for directory in layout_directories:
        _ensure_layout_directory(directory)

    return paths


def _ensure_layout_directory(path: Path) -> None:
    """Create one global-layout directory with the required POSIX creation mode."""
    try:
        path.mkdir(mode=0o755, exist_ok=True)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot create global Worktree directory '{path}': {exc}. Check directory permissions."
        ) from exc
