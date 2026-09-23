"""Atomic persistence and loading of session run payloads."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem import Filesystem
from worktree.core.diff.writer import get_session_dir, write_session_diff
from worktree.core.engine.models import SessionRunPayload
from worktree.core.project.services.storage import resolve_project_filesystem_paths


def write_session_run_json(session_dir: Path, payload: SessionRunPayload) -> Path:
    """Atomically write run metadata and step results to run.json."""
    target_file = session_dir / "run.json"
    Filesystem.atomic_write_text(target_file, payload.model_dump_json(indent=2))
    return target_file


def load_session_run(path: Path, session_id: str) -> SessionRunPayload | None:
    """Load and parse project-aware session run metadata when present and valid."""
    target_file = resolve_project_filesystem_paths(path).session_dir(session_id) / "run.json"
    if not target_file.is_file():
        return None
    try:
        content = target_file.read_text(encoding="utf-8")
        return SessionRunPayload.model_validate_json(content)
    except Exception:
        return None


__all__ = [
    "get_session_dir",
    "load_session_run",
    "write_session_diff",
    "write_session_run_json",
]
