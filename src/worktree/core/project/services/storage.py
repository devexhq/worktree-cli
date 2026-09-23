"""Project-aware workspace runtime storage resolution."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem.models import FilesystemPaths
from worktree.core.project.services.identity import load_project_identity


def resolve_project_filesystem_paths(root_dir: Path) -> FilesystemPaths:
    """Resolve workspace paths using the persisted project identity when available."""
    local_paths = FilesystemPaths.from_root(root_dir)
    identity_result = load_project_identity(local_paths.worktree_dir / "project.json")
    if identity_result.ok and identity_result.identity is not None:
        return FilesystemPaths.from_root(local_paths.root_dir, project_id=identity_result.identity.id)

    return local_paths
