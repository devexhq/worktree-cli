"""Unit tests for core diff services and renderers."""

from __future__ import annotations

import os
import time
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from tests.helpers import FileSystem, make_rich_output
from worktree.common.utils import RichOutput
from worktree.core.config.models import ProjectConfig, WorktreeConfig
from worktree.core.diff.models import DiffResult, DiffStatus
from worktree.core.diff.renderers import (
    render_diff,
    render_diff_not_found,
    render_diff_success,
    render_empty_diff,
    render_read_failure,
    render_session_not_found,
)
from worktree.core.diff.services import DiffService

_SAMPLE_DIFF = """diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
-old line
+new line
"""


class DiffRenderersTests:
    """Unit tests for diff Rich renderers."""

    def test_render_session_not_found_explicit(self) -> None:
        """Verify render_session_not_found with explicit session ID."""
        output, buffer = make_rich_output()
        render_session_not_found("sbx_missing_123", output=output)
        output.print()
        text = buffer.getvalue()
        assert "Session Not Found" in text
        assert "Session 'sbx_missing_123' not found" in text

    def test_render_session_not_found_implicit(self) -> None:
        """Verify render_session_not_found with no session ID."""
        output, buffer = make_rich_output()
        render_session_not_found(None, output=output)
        output.print()
        text = buffer.getvalue()
        assert "Session Not Found" in text
        assert "No loop run sessions found." in text

    def test_render_diff_not_found(self) -> None:
        """Verify render_diff_not_found formats error panel with fix hint."""
        output, buffer = make_rich_output()
        render_diff_not_found("sbx_no_diff", output=output)
        output.print()
        text = buffer.getvalue()
        assert "Diff Not Found" in text
        assert "Session 'sbx_no_diff' has no diff artifact." in text
        assert ".worktree/sessions/sbx_no_diff/diff.patch" in text

    def test_render_read_failure(self) -> None:
        """Verify render_read_failure formats error panel."""
        output, buffer = make_rich_output()
        render_read_failure("Permission denied", output=output)
        output.print()
        text = buffer.getvalue()
        assert "Read Failure" in text
        assert "Permission denied" in text

    def test_render_empty_diff(self) -> None:
        """Verify render_empty_diff renders single-line message."""
        output, buffer = make_rich_output()
        render_empty_diff("sbx_empty", output=output)
        output.print()
        text = buffer.getvalue()
        assert "No changes recorded for session sbx_empty." in text

    def test_render_diff_success_formatted(self) -> None:
        """Verify render_diff_success with raw=False renders header and syntax."""
        output, buffer = make_rich_output()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_ok_123",
            artifact_path=Path("/repo/.worktree/sessions/sbx_ok_123/diff.patch"),
            diff_text=_SAMPLE_DIFF,
        )
        render_diff_success(result, raw=False, output=output, cwd=Path("/repo"))
        output.print()
        text = buffer.getvalue()
        assert "Session: sbx_ok_123 (.worktree/sessions/sbx_ok_123/diff.patch)" in text
        assert "-old line" in text
        assert "+new line" in text

    def test_render_diff_success_raw(self) -> None:
        """Verify render_diff_success with raw=True outputs plain diff without header."""
        output, buffer = make_rich_output()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_ok_123",
            artifact_path=Path("/repo/.worktree/sessions/sbx_ok_123/diff.patch"),
            diff_text=_SAMPLE_DIFF,
        )
        render_diff_success(result, raw=True, output=output)
        output.print()
        text = buffer.getvalue()
        assert "Session: sbx_ok_123" not in text
        assert _SAMPLE_DIFF.strip() in text

    def test_render_diff_truncation_in_tty(self) -> None:
        """Verify diff > 500 lines in TTY is truncated at line 500 with notice banner."""
        buffer = StringIO()
        tty_console = Console(file=buffer, force_terminal=True, color_system=None, width=120)
        output = RichOutput(console=tty_console)

        lines = [f"+line {i}" for i in range(1, 601)]
        diff_text = "\n".join(lines)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_large_1",
            artifact_path=Path("/repo/.worktree/sessions/sbx_large_1/diff.patch"),
            diff_text=diff_text,
        )

        render_diff_success(result, output=output, cwd=Path("/repo"))
        output.print()
        text = buffer.getvalue()

        assert "+line 1" in text
        assert "+line 500" in text
        assert "+line 501" not in text
        assert "... [diff truncated: showing 500 of 600 lines]" in text
        assert "Hint:" in text
        assert "run `wt diff sbx_large_1 --full` to view complete formatted output" in text
        assert "run `wt diff sbx_large_1 --full | less -R` to page through formatted diff" in text
        assert "run `wt diff sbx_large_1 --raw` to output unformatted patch text" in text
        assert "inspect artifact at .worktree/sessions/sbx_large_1/diff.patch" in text

    def test_render_diff_full_override_in_tty(self) -> None:
        """Verify diff > 500 lines with full=True renders complete output without notice banner."""
        buffer = StringIO()
        tty_console = Console(file=buffer, force_terminal=True, color_system=None, width=120)
        output = RichOutput(console=tty_console)

        lines = [f"+line {i}" for i in range(1, 601)]
        diff_text = "\n".join(lines)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_large_2",
            artifact_path=Path("/repo/.worktree/sessions/sbx_large_2/diff.patch"),
            diff_text=diff_text,
        )

        render_diff_success(result, full=True, output=output, cwd=Path("/repo"))
        output.print()
        text = buffer.getvalue()

        assert "+line 1" in text
        assert "+line 500" in text
        assert "+line 600" in text
        assert "diff truncated" not in text

    def test_render_diff_non_tty_bypass_truncation(self) -> None:
        """Verify non-TTY environments bypass truncation completely."""
        output, buffer = make_rich_output()  # force_terminal=False

        lines = [f"+line {i}" for i in range(1, 601)]
        diff_text = "\n".join(lines)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_large_3",
            artifact_path=Path("/repo/.worktree/sessions/sbx_large_3/diff.patch"),
            diff_text=diff_text,
        )

        render_diff_success(result, output=output, cwd=Path("/repo"))
        output.print()
        text = buffer.getvalue()

        assert "+line 1" in text
        assert "+line 600" in text
        assert "diff truncated" not in text

    def test_render_diff_custom_max_lines(self) -> None:
        """Verify custom max_lines threshold is respected in TTY."""
        buffer = StringIO()
        tty_console = Console(file=buffer, force_terminal=True, color_system=None, width=120)
        output = RichOutput(console=tty_console)

        lines = [f"+line {i}" for i in range(1, 50)]
        diff_text = "\n".join(lines)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_custom_max",
            artifact_path=Path("/repo/.worktree/sessions/sbx_custom_max/diff.patch"),
            diff_text=diff_text,
        )

        render_diff_success(result, max_lines=10, output=output, cwd=Path("/repo"))
        output.print()
        text = buffer.getvalue()

        assert "+line 10" in text
        assert "+line 11" not in text
        assert "... [diff truncated: showing 10 of 49 lines]" in text

    def test_render_diff_invalid_max_lines_fallback(self) -> None:
        """Verify non-positive or invalid max_lines falls back to DEFAULT_MAX_DIFF_LINES."""
        buffer = StringIO()
        tty_console = Console(file=buffer, force_terminal=True, color_system=None, width=120)
        output = RichOutput(console=tty_console)

        lines = [f"+line {i}" for i in range(1, 601)]
        diff_text = "\n".join(lines)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_fallback",
            artifact_path=Path("/repo/.worktree/sessions/sbx_fallback/diff.patch"),
            diff_text=diff_text,
        )

        render_diff_success(result, max_lines=-10, output=output, cwd=Path("/repo"))

        output.print()
        text = buffer.getvalue()

        assert "+line 500" in text
        assert "+line 501" not in text
        assert "... [diff truncated: showing 500 of 600 lines]" in text

    def test_render_diff_dispatcher(self) -> None:
        """Verify render_diff routes each DiffStatus correctly."""
        output, buffer = make_rich_output()

        res_sess_nf = DiffResult(status=DiffStatus.SESSION_NOT_FOUND, session_id="s1")
        render_diff(res_sess_nf, output=output)

        res_diff_nf = DiffResult(status=DiffStatus.DIFF_NOT_FOUND, session_id="s2")
        render_diff(res_diff_nf, output=output)

        res_read_fail = DiffResult(status=DiffStatus.READ_FAILURE, errors=["Read error"])
        render_diff(res_read_fail, output=output)

        res_empty = DiffResult(status=DiffStatus.EMPTY_DIFF, session_id="s3")
        render_diff(res_empty, output=output)

        output.print()
        text = buffer.getvalue()
        assert "Session 's1' not found" in text
        assert "Session 's2' has no diff artifact." in text
        assert "Read error" in text
        assert "No changes recorded for session s3." in text


class DiffServiceTests:
    """Unit tests for DiffService data collection and execution."""

    def test_collect_no_config_falls_back_to_default_path(self, fs: FileSystem) -> None:
        """Verify collect without config uses .worktree/sessions as the default sessions path."""
        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output)
        result = service.collect()
        assert not result.ok
        # No config and no sessions directory: SESSION_NOT_FOUND (not NOT_INITIALIZED)
        assert result.status == DiffStatus.SESSION_NOT_FOUND

    def test_collect_uses_injected_config_sessions_dir(self, fs: FileSystem) -> None:
        """Verify collect uses config.paths.sessions_dir from the injected WorktreeConfig."""
        config = WorktreeConfig(version=1, project=ProjectConfig(name="test"))
        patch_file = fs.base_path / config.paths.sessions_dir / "sbx_cfg" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_cfg", config=config)
        result = service.collect()
        assert result.ok
        assert result.status == DiffStatus.OK
        assert result.diff_text == _SAMPLE_DIFF

    def test_collect_explicit_session_missing_dir(self, fs: FileSystem) -> None:
        """Verify collect returns SESSION_NOT_FOUND when explicit session directory is absent."""
        fs.create_config_file()
        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_unknown")
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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_nodiff")
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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_unreadable")

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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_empty")
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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_valid")
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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output)
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

        output = RichOutput()
        service = DiffService(path=fs.base_path, output=output)
        result = service.collect()
        assert not result.ok
        assert result.status == DiffStatus.SESSION_NOT_FOUND
        assert any("No loop run sessions found." in e for e in result.errors)

    def test_execute_renders_to_output(self, fs: FileSystem) -> None:
        """Verify execute calls collect and renders to Rich output."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_exec" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        output, buffer = make_rich_output()
        service = DiffService(path=fs.base_path, output=output, session_id="sbx_exec", raw=False)
        result = service.execute()
        assert result.ok
        output.print()
        text = buffer.getvalue()
        assert "Session: sbx_exec" in text
        assert "new line" in text
