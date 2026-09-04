"""Unit tests for core diff services."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.config import ConfigLoadError
from worktree.core.diff.models import DiffStatus
from worktree.core.diff.services import DiffService

_SAMPLE_DIFF = """diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
-old line
+new line
"""


class DiffServiceTests:
    """Unit tests for DiffService data collection and execution."""

    def test_collect_no_config_raises_on_missing_config(self, fs: FileSystem) -> None:
        """Verify collect without config raises ConfigLoadError."""
        service = DiffService(path=fs.base_path)
        with pytest.raises(ConfigLoadError):
            service.collect()

    def test_collect_uses_config_sessions_dir(self, fs: FileSystem) -> None:
        """Verify collect uses config.paths.sessions_dir from loaded configuration."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_cfg" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        service = DiffService(path=fs.base_path, session_id="sbx_cfg")
        result = service.collect()
        assert result.ok
        assert result.status == DiffStatus.OK
        assert result.diff_text == _SAMPLE_DIFF

    def test_collect_explicit_session_missing_dir(self, fs: FileSystem) -> None:
        """Verify collect returns SESSION_NOT_FOUND when explicit session directory is absent."""
        fs.create_config_file()
        service = DiffService(path=fs.base_path, session_id="sbx_unknown")
        result = service.collect()
        assert not result.ok
        assert result.status == DiffStatus.SESSION_NOT_FOUND
        assert result.session_id == "sbx_unknown"
        assert any("sbx_unknown" in e for e in result.errors)

    def test_collect_explicit_session_missing_diff_patch(self, fs: FileSystem) -> None:
        """Verify collect returns DIFF_NOT_FOUND when diff.patch does not exist."""
        fs.create_config_file()
        session_dir = fs.base_path / ".worktree" / "sessions" / "sbx_nodiff"
        session_dir.mkdir(parents=True, exist_ok=True)

        service = DiffService(path=fs.base_path, session_id="sbx_nodiff")
        result = service.collect()
        assert not result.ok
        assert result.status == DiffStatus.DIFF_NOT_FOUND
        assert result.session_id == "sbx_nodiff"
        assert any("no diff artifact" in e for e in result.errors)

    def test_collect_explicit_session_unreadable_diff(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify collect returns READ_FAILURE on read error."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_unreadable" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        service = DiffService(path=fs.base_path, session_id="sbx_unreadable")

        orig_read_text = Path.read_text

        def _custom_read_text(self_path: Path, *args: object, **kwargs: object) -> str:
            if self_path.name == "diff.patch":
                raise OSError("Disk read failure")
            return orig_read_text(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _custom_read_text)
        result = service.collect()

        assert not result.ok
        assert result.status == DiffStatus.READ_FAILURE
        assert any("Disk read failure" in e for e in result.errors)

    def test_collect_explicit_session_empty_diff(self, fs: FileSystem) -> None:
        """Verify collect returns EMPTY_DIFF (ok=True) when diff.patch is empty or whitespace."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_empty" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text("   \n\t\n", encoding="utf-8")

        service = DiffService(path=fs.base_path, session_id="sbx_empty")
        result = service.collect()
        assert result.ok
        assert result.status == DiffStatus.EMPTY_DIFF
        assert result.session_id == "sbx_empty"
        assert result.diff_text == ""

    def test_collect_explicit_session_valid_diff(self, fs: FileSystem) -> None:
        """Verify collect returns OK when diff.patch contains unified diff content."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_valid" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        service = DiffService(path=fs.base_path, session_id="sbx_valid")
        result = service.collect()
        assert result.ok
        assert result.status == DiffStatus.OK
        assert result.session_id == "sbx_valid"
        assert result.diff_text == _SAMPLE_DIFF

    def test_collect_implicit_latest_session_discovery(self, fs: FileSystem) -> None:
        """Verify collect auto-discovers the latest session directory by mtime."""
        fs.create_config_file()
        sessions_root = fs.base_path / ".worktree" / "sessions"

        sess_1 = sessions_root / "sbx_older"
        sess_1.mkdir(parents=True, exist_ok=True)
        (sess_1 / "diff.patch").write_text("old diff", encoding="utf-8")

        # Set older timestamp
        os.utime(sess_1, (time.time() - 100, time.time() - 100))

        sess_2 = sessions_root / "sbx_newer"
        sess_2.mkdir(parents=True, exist_ok=True)
        (sess_2 / "diff.patch").write_text(_SAMPLE_DIFF, encoding="utf-8")
        os.utime(sess_2, (time.time(), time.time()))

        service = DiffService(path=fs.base_path)
        result = service.collect()
        assert result.ok
        assert result.status == DiffStatus.OK
        assert result.session_id == "sbx_newer"
        assert result.diff_text == _SAMPLE_DIFF

    def test_collect_implicit_no_sessions_found(self, fs: FileSystem) -> None:
        """Verify collect returns SESSION_NOT_FOUND when sessions directory is empty."""
        fs.create_config_file()
        sessions_root = fs.base_path / ".worktree" / "sessions"
        sessions_root.mkdir(parents=True, exist_ok=True)

        service = DiffService(path=fs.base_path)
        result = service.collect()
        assert not result.ok
        assert result.status == DiffStatus.SESSION_NOT_FOUND
        assert any("No loop run sessions found." in e for e in result.errors)

    def test_execute_renders_to_output(self, fs: FileSystem) -> None:
        """Verify execute calls collect and returns DiffResult."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_exec" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        service = DiffService(path=fs.base_path, session_id="sbx_exec", raw=False)
        result = service.execute()
        assert result.ok
        assert result.session_id == "sbx_exec"
        assert result.diff_text == _SAMPLE_DIFF
