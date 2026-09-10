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
    namespace: str | None = None
    error: str | None = None
    parsed: Any | None = None
    content: str | None = ""
    checksum: str | None = None
    file_size: int | None = None


class FilesystemPaths(BaseModel):
    """Single source of truth for all resolved workspace paths."""

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    root_path: Path
    worktree_path: Path
    config_file: Path
    db_file: Path
    catalog_path: Path
    catalog_steps_path: Path
    catalog_blueprints_path: Path
    logs_path: Path
    sessions_path: Path
    artifacts_path: Path
    tmp_path: Path
    sandboxes_path: Path
    lock_file: Path
    gitignore_file: Path
    catalog_templates_path: Traversable

    @classmethod
    def from_root(cls, root_dir: Path) -> FilesystemPaths:
        """Construct canonical workspace path hierarchy rooted at root_dir."""
        canonical_root = root_dir.expanduser().resolve()
        wt = canonical_root if canonical_root.name == ".worktree" else canonical_root / ".worktree"
        root_path = canonical_root.parent if canonical_root.name == ".worktree" else canonical_root

        return cls(
            root_path=root_path,
            worktree_path=wt,
            config_file=wt / "config.json",
            db_file=wt / "data.db",
            catalog_path=wt / "catalog",
            catalog_steps_path=wt / "catalog" / "steps",
            catalog_blueprints_path=wt / "catalog" / "blueprints",
            logs_path=wt / "logs",
            sessions_path=wt / "sessions",
            artifacts_path=wt / "artifacts",
            tmp_path=wt / "tmp",
            sandboxes_path=wt / "sandboxes",
            lock_file=wt / "worktree.lock",
            gitignore_file=root_path / ".gitignore",
            catalog_templates_path=importlib.resources.files("worktree.core.catalog.templates"),
        )

    def session_dir(self, session_id: str) -> Path:
        """Return path to a specific session directory."""
        return self.sessions_path / session_id

    def sandbox_dir(self, sandbox_id: str) -> Path:
        """Return path to a specific sandbox directory."""
        return self.sandboxes_path / sandbox_id

    def rel_to_root(self, path: Path | str) -> Path:
        """Return path relative to workspace root."""
        try:
            return Path(path).resolve().relative_to(self.root_path)
        except ValueError:
            return Path(path)
