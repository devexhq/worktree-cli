"""Session artifact directory and diff persistence helpers."""

from __future__ import annotations

import os
from pathlib import Path


def get_session_dir(path: Path, session_id: str, sessions_dir: str = ".worktree/sessions") -> Path:
    """Resolve and create session artifact directory on demand."""
    target = path / sessions_dir / session_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_session_diff(session_dir: Path, diff_text: str) -> Path:
    """Atomically write unified diff to diff.patch in the session directory."""
    target_file = session_dir / "diff.patch"
    tmp_file = session_dir / "diff.patch.tmp"
    tmp_file.write_text(diff_text, encoding="utf-8")
    os.replace(tmp_file, target_file)
    return target_file
