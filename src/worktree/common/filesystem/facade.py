from __future__ import annotations

from pathlib import Path
from typing import Any

from worktree.common.filesystem.models import FilesystemPaths, YamlFile
from worktree.common.filesystem.services.git import (
    is_git_repository as _is_git_repository,
    update_gitignore as _update_gitignore,
)
from worktree.common.filesystem.services.operations import (
    atomic_write_json as _atomic_write_json,
    atomic_write_text as _atomic_write_text,
    compute_content_checksum as _compute_content_checksum,
    delete_file as _delete_file,
)
from worktree.common.filesystem.services.paths import find_worktree_root as _find_worktree_root
from worktree.common.filesystem.services.yaml import (
    read_yaml_file as _read_yaml_file,
    scan_yaml_directory as _scan_yaml_directory,
)


class Filesystem:
    """Unified entrypoint for workspace filesystem paths, caching, and atomic I/O."""

    _instance: Filesystem | None = None
    _configured_root: Path | None = None
    _raw_path: Path | None = None
    _cached_paths: FilesystemPaths | None = None

    def __new__(cls, path: Path | str | None = None) -> Filesystem:
        """Return singleton instance when path is omitted, or create a specific instance when path is provided."""
        if path is None:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialize(cls._configured_root)
                cls._instance = instance
            return cls._instance

        instance = super().__new__(cls)
        instance._initialize(path)
        return instance

    def _initialize(self, path: Path | str | None = None) -> None:
        self._raw_path: Path | None = Path(path) if path is not None else None
        self._cached_paths: FilesystemPaths | None = None

    @classmethod
    def configure(cls, root: Path | str | None = None) -> Filesystem:
        """Configure the process-level workspace root and return the active Filesystem singleton."""
        if root is not None:
            resolved = Path(root).expanduser().resolve()
            cls._configured_root = _find_worktree_root(resolved)
        else:
            cls._configured_root = None
        cls._instance = None
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the process-level singleton and configured root."""
        cls._instance = None
        cls._configured_root = None

    @classmethod
    def instance(cls) -> Filesystem:
        """Return the active singleton instance."""
        return cls()

    @property
    def paths(self) -> FilesystemPaths:
        """Resolved and cached single source of truth for all workspace paths."""
        if self._cached_paths is None:
            resolved_root = _find_worktree_root(self._raw_path)
            self._cached_paths = FilesystemPaths.from_root(resolved_root)
        return self._cached_paths

    def __getattr__(self, name: str) -> Any:
        """Delegate path and helper lookups directly to self.paths."""
        paths = self.paths
        if hasattr(paths, name):
            return getattr(paths, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __repr__(self) -> str:
        return f"Filesystem(root={self.paths.root_dir!r})"

    # Bound instance methods
    def write_text(self, path: Path, text: str) -> None:
        """Write text content atomically with UTF-8 encoding."""
        _atomic_write_text(path, text)

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON content atomically with indent=2, UTF-8, and trailing newline."""
        _atomic_write_json(path, data)

    def delete_file(self, path: Path) -> bool:
        """Delete a file if it exists. Returns True if the file existed before deletion."""
        return _delete_file(path)

    def read_yaml(self, path: Path) -> YamlFile:
        """Read and parse a YAML file into a typed YamlFile model."""
        return _read_yaml_file(path)

    def scan_yaml(self, directory: Path, *, suffixes: tuple[str, ...] = (".yml", ".yaml")) -> list[YamlFile]:
        """Scan a directory recursively for matching YAML files, sorted by path."""
        return _scan_yaml_directory(directory, suffixes=suffixes)

    def update_gitignore(self, path: Path | None = None) -> bool:
        """Ensure /.worktree/ is excluded in .gitignore."""
        target = path if path is not None else self.paths.gitignore_file
        return _update_gitignore(target)

    def is_git_repo(self, path: Path | None = None) -> bool:
        """Check whether the given directory contains a .git directory or file."""
        target = path if path is not None else self.paths.root_dir
        return _is_git_repository(target)

    def checksum(self, content: str) -> str:
        """Compute SHA-256 hex digest of string content."""
        return _compute_content_checksum(content)

    # Static helpers for standalone execution
    @staticmethod
    def find_root(start: Path | None = None) -> Path:
        """Find the root directory of a worktree workspace or git repository."""
        return _find_worktree_root(start)

    @staticmethod
    def is_git_repository(path: Path) -> bool:
        """Check whether the given directory contains a .git directory or file."""
        return _is_git_repository(path)

    @staticmethod
    def update_gitignore_file(path: Path) -> bool:
        """Ensure /.worktree/ is excluded in the specified .gitignore file."""
        return _update_gitignore(path)

    @staticmethod
    def atomic_write_text(path: Path, text: str) -> None:
        """Write text content atomically with UTF-8 encoding."""
        _atomic_write_text(path, text)

    @staticmethod
    def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
        """Write JSON content atomically with indent=2, UTF-8, and trailing newline."""
        _atomic_write_json(path, data)

    @staticmethod
    def compute_checksum(content: str) -> str:
        """Compute SHA-256 hex digest of string content."""
        return _compute_content_checksum(content)

    @staticmethod
    def read_yaml_file(file_path: Path) -> YamlFile:
        """Read and parse a YAML file into a typed YamlFile model."""
        return _read_yaml_file(file_path)

    @staticmethod
    def scan_yaml_directory(directory: Path, *, suffixes: tuple[str, ...] = (".yml", ".yaml")) -> list[YamlFile]:
        """Scan a directory recursively for matching YAML files, sorted by path."""
        return _scan_yaml_directory(directory, suffixes=suffixes)
