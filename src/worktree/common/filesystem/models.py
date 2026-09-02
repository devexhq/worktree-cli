from __future__ import annotations

import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class YamlFile(BaseModel):
    """Container for parsed YAML file metadata and content."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    path: Path
    error: str | None = None
    parsed: Any | None = None
    content: str | None = ""
    checksum: str | None = None
    file_size: int | None = None


class FilesystemPaths(BaseModel):
    """Single source of truth for all resolved workspace paths."""

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    root_dir: Path
    worktree_dir: Path
    config_file: Path
    db_file: Path
    catalog_dir: Path
    logs_dir: Path
    sessions_dir: Path
    artifacts_dir: Path
    tmp_dir: Path
    sandboxes_dir: Path
    lock_file: Path
    gitignore_file: Path
    catalog_templates_dir: Traversable

    @classmethod
    def from_root(cls, root_dir: Path) -> FilesystemPaths:
        """Construct canonical workspace path hierarchy rooted at root_dir."""
        canonical_root = root_dir.expanduser().resolve()
        wt = canonical_root if canonical_root.name == ".worktree" else canonical_root / ".worktree"
        project_root = canonical_root.parent if canonical_root.name == ".worktree" else canonical_root

        return cls(
            root_dir=project_root,
            worktree_dir=wt,
            config_file=wt / "config.json",
            db_file=wt / "data.db",
            catalog_dir=wt / "catalog",
            logs_dir=wt / "logs",
            sessions_dir=wt / "sessions",
            artifacts_dir=wt / "artifacts",
            tmp_dir=wt / "tmp",
            sandboxes_dir=wt / "sandboxes",
            lock_file=wt / "worktree.lock",
            gitignore_file=project_root / ".gitignore",
            catalog_templates_dir=importlib.resources.files("worktree.core.catalog.templates"),
        )

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
