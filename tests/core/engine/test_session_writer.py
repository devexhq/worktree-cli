"""Unit tests for atomic session writer services."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.diff.writer import get_session_dir, write_session_diff
from worktree.core.engine.models import SessionRunPayload
from worktree.core.engine.writer import (
    load_session_run,
    write_session_run_json,
)
from worktree.core.step.models import StepResult

_SAMPLE_DIFF = """diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1 +1 @@
-old
+new
"""


class SessionWriterTests:
    """Unit tests for session writer helpers."""

    def test_get_session_dir_creates_dir(self, fs: FileSystem) -> None:
        """Verify get_session_dir creates the target session directory."""
        target = get_session_dir(fs.base_path, "sess_123")
        assert target.is_dir()
        assert target == fs.base_path / ".worktree" / "sessions" / "sess_123"

    def test_write_session_diff_atomic(self, fs: FileSystem) -> None:
        """Verify write_session_diff writes diff.patch atomically."""
        session_dir = get_session_dir(fs.base_path, "sess_diff")
        patch_file = write_session_diff(session_dir, _SAMPLE_DIFF)
        assert patch_file.is_file()
        assert patch_file.name == "diff.patch"
        assert patch_file.read_text(encoding="utf-8") == _SAMPLE_DIFF
        assert not (session_dir / "diff.patch.tmp").exists()

    def test_write_session_diff_empty(self, fs: FileSystem) -> None:
        """Verify write_session_diff handles empty diff string."""
        session_dir = get_session_dir(fs.base_path, "sess_empty_diff")
        patch_file = write_session_diff(session_dir, "")
        assert patch_file.is_file()
        assert patch_file.read_text(encoding="utf-8") == ""

    def test_write_and_load_session_run_json(self, fs: FileSystem) -> None:
        """Verify write_session_run_json and load_session_run roundtrip."""
        session_dir = get_session_dir(fs.base_path, "sess_run_json")
        step_res = StepResult(
            step_id="step-1",
            status="completed",
            exit_code=0,
            stdout="hi\n",
            stderr="",
            duration_seconds=0.12,
            attempts=1,
        )
        payload = SessionRunPayload(
            version=1,
            session_id="sess_run_json",
            kind="task",
            name="my-task",
            status="completed",
            started_at="2026-08-29T12:00:00Z",
            completed_at="2026-08-29T12:00:05Z",
            error_message=None,
            step_results=[step_res],
        )
        run_file = write_session_run_json(session_dir, payload)
        assert run_file.is_file()
        assert run_file.name == "run.json"

        loaded = load_session_run(fs.base_path, "sess_run_json")
        assert loaded is not None
        assert loaded.session_id == "sess_run_json"
        assert loaded.kind == "task"
        assert loaded.name == "my-task"
        assert loaded.status == "completed"
        assert len(loaded.step_results) == 1
        assert loaded.step_results[0].stdout == "hi\n"

    def test_load_session_run_missing(self, fs: FileSystem) -> None:
        """Verify load_session_run returns None when file does not exist."""
        loaded = load_session_run(fs.base_path, "nonexistent")
        assert loaded is None

    def test_load_session_run_corrupt(self, fs: FileSystem) -> None:
        """Verify load_session_run returns None on corrupt JSON."""
        session_dir = get_session_dir(fs.base_path, "sess_corrupt")
        (session_dir / "run.json").write_text("{invalid json", encoding="utf-8")

        loaded = load_session_run(fs.base_path, "sess_corrupt")
        assert loaded is None
