from __future__ import annotations

import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class YamlFile(BaseModel):
    """Container for parsed YAML file metadata and content."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    path: Path
    namespace: str | None = None
    error: str | None = None
    parsed: Any | None = None
    content: str | None = ""
    checksum: str | None = None
    file_size: int | None = None


@runtime_checkable
class _GlobalRootModule(Protocol):
    """Typed interface for the deferred global-root resolver import."""

    def resolve_global_paths(self) -> GlobalPaths:
        """Resolve the configured global Worktree path hierarchy."""
        ...


class FilesystemPaths(BaseModel):
    """Single source of truth for all resolved workspace paths."""

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    root_dir: Path
    worktree_dir: Path
    config_file: Path
    db_file: Path
    catalog_dir: Path
    catalog_steps_dir: Path
    catalog_blueprints_dir: Path
    logs_dir: Path
    sessions_dir: Path
    artifacts_dir: Path
    tmp_dir: Path
    sandboxes_dir: Path
    lock_file: Path
    gitignore_file: Path
    catalog_templates_dir: Traversable
    project_id: str | None = None

    @classmethod
    def from_root(cls, root_dir: Path, project_id: str | None = None) -> FilesystemPaths:
        """Construct workspace paths with optional project-global runtime storage."""
        canonical_root = root_dir.expanduser().resolve()
        wt = canonical_root if canonical_root.name == ".worktree" else canonical_root / ".worktree"
        root_path = canonical_root.parent if canonical_root.name == ".worktree" else canonical_root
        runtime_root = wt
        if project_id is not None:
            global_root_module = importlib.import_module("worktree.common.filesystem.services.global_root")
            if not isinstance(global_root_module, _GlobalRootModule):
                raise TypeError("Global root resolver is unavailable.")
            runtime_root = global_root_module.resolve_global_paths().storage_dir / "projects" / project_id

        return cls(
            root_dir=root_path,
            worktree_dir=wt,
            config_file=wt / "config.json",
            db_file=wt / "data.db",
            catalog_dir=wt / "catalog",
            catalog_steps_dir=wt / "catalog" / "steps",
            catalog_blueprints_dir=wt / "catalog" / "blueprints",
            logs_dir=runtime_root / "logs",
            sessions_dir=runtime_root / "sessions",
            artifacts_dir=runtime_root / "artifacts",
            tmp_dir=runtime_root / "tmp",
            sandboxes_dir=wt / "sandboxes",
            lock_file=wt / "worktree.lock",
            gitignore_file=root_path / ".gitignore",
            catalog_templates_dir=importlib.resources.files("worktree.core.catalog.templates"),
            project_id=project_id,
        )

    def project_storage_dir(self) -> Path | None:
        """Return the project-global runtime root when a project identifier is active."""
        if self.project_id is None:
            return None
        return self.sessions_dir.parent

    def session_dir(self, session_id: str) -> Path:
        """Return path to a specific session directory."""
        return self.sessions_dir / session_id

    def sandbox_dir(self, sandbox_id: str) -> Path:
        """Return path to a specific sandbox directory."""
        return self.sandboxes_dir / sandbox_id

    def rel_to_root(self, path: Path | str) -> Path:
        """Return path relative to workspace root."""
        try:
            return Path(path).resolve().relative_to(self.root_dir)
        except ValueError:
            return Path(path)


class GlobalPaths(BaseModel):
    """Paths for global ~/.worktree hierarchy."""

    model_config = ConfigDict(extra="forbid", strict=True)

    root: Path
    global_dir: Path
    global_catalog_dir: Path
    user_dir: Path
    user_catalog_dir: Path
    data_dir: Path
    storage_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> GlobalPaths:
        """Construct the canonical global Worktree path hierarchy."""
        canonical_root = root.expanduser().resolve()
        return cls(
            root=canonical_root,
            global_dir=canonical_root / "global",
            global_catalog_dir=canonical_root / "global" / "catalog",
            user_dir=canonical_root / "user",
            user_catalog_dir=canonical_root / "user" / "catalog",
            data_dir=canonical_root / "data",
            storage_dir=canonical_root / "storage",
        )
