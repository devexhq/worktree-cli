"""Atomic persistence and loading of session run payloads."""

from __future__ import annotations

import os
from pathlib import Path

from worktree.core.diff.writer import get_session_dir, write_session_diff
from worktree.core.engine.models import SessionRunPayload


def write_session_run_json(session_dir: Path, payload: SessionRunPayload) -> Path:
    """Atomically write run metadata and step results to run.json."""
    target_file = session_dir / "run.json"
    tmp_file = session_dir / "run.json.tmp"
    tmp_file.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_file, target_file)
    return target_file


def load_session_run(path: Path, session_id: str, sessions_dir: str = ".worktree/sessions") -> SessionRunPayload | None:
    """Load and parse session run.json if present and valid."""
    target_file = path / sessions_dir / session_id / "run.json"
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
