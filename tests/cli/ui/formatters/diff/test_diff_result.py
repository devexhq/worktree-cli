"""Tier 2 presentation contract tests for DiffResultFormatter."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from tests.helpers import render_rich
from worktree.cli.ui.formatters.diff import DiffResultFormatter
from worktree.core.diff.models import DiffResult, DiffStatus

_SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass  # intentionally long line exceeding 120 characters to ensure diff raw output does not wrap at terminal columns boundaries
"""


class DiffResultFormatterTests:
    """Presentation contract tests for DiffResultFormatter."""

    def test_to_rich_when_ok_renders_diff_text(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_fmt_1",
            artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_1/diff.patch"),
            diff_text=_SAMPLE_DIFF,
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_fmt_1" in rendered
        assert "def old(): pass" in rendered
        assert "def new(): pass" in rendered

    def test_to_rich_when_empty_diff_renders_session_id(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.EMPTY_DIFF,
            session_id="sbx_fmt_empty",
            artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_empty/diff.patch"),
            diff_text="",
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_fmt_empty" in rendered

    def test_to_rich_when_session_not_found_renders_session_id(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            session_id="sbx_missing_99",
            errors=["Session 'sbx_missing_99' not found under .worktree/sessions/."],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_missing_99" in rendered

    def test_to_rich_when_no_sessions_found_renders_error_message(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            errors=["No loop run sessions found."],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "No loop run sessions found." in rendered

    def test_to_rich_when_diff_not_found_renders_session_id(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.DIFF_NOT_FOUND,
            session_id="sbx_no_patch_artifact",
            errors=["Session 'sbx_no_patch_artifact' has no diff artifact."],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_no_patch_artifact" in rendered

    def test_to_rich_when_read_failure_renders_error_message(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.READ_FAILURE,
            session_id="sbx_corrupt",
            errors=["Failed to read diff artifact at '...': Permission denied"],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "Permission denied" in rendered

    def test_to_rich_when_general_error_renders_error_message(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            errors=["Unexpected internal failure"],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "Unexpected internal failure" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_json_1",
            artifact_path=Path("/tmp/diff.patch"),
            diff_text=_SAMPLE_DIFF,
            warnings=["Non-critical warning"],
        )

        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "session_id": "sbx_json_1",
            "artifact_path": "/tmp/diff.patch",
            "diff_text": _SAMPLE_DIFF,
            "raw": False,
            "full": False,
            "max_lines": None,
            "warnings": ["Non-critical warning"],
            "errors": [],
            "fixes": [],
        }

        # Verify JSON encoding works without errors
        encoded = json.dumps(dumped)
        decoded = json.loads(encoded)
        assert decoded["session_id"] == "sbx_json_1"

    def test_to_raw_when_raw_returns_diff_text(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_raw_1",
            artifact_path=Path("/repo/.worktree/sessions/sbx_raw_1/diff.patch"),
            diff_text=_SAMPLE_DIFF,
            raw=True,
        )

        raw_output = formatter.to_raw(result)
        assert raw_output == _SAMPLE_DIFF

    def test_to_raw_when_empty_diff_renders_session_id(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.EMPTY_DIFF,
            session_id="sbx_raw_empty",
            artifact_path=Path("/repo/.worktree/sessions/sbx_raw_empty/diff.patch"),
            diff_text="",
        )

        raw_output = formatter.to_raw(result)
        assert "sbx_raw_empty" in raw_output

    def test_to_raw_when_session_not_found_renders_session_id(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            session_id="sbx_missing_raw",
            errors=["Session 'sbx_missing_raw' not found under .worktree/sessions/."],
        )

        raw_output = formatter.to_raw(result)
        assert "sbx_missing_raw" in raw_output

    def test_to_raw_and_rich_when_tty_truncates_lines(self) -> None:
        forced_tty_console = Console(force_terminal=True)
        formatter = DiffResultFormatter(console=forced_tty_console, max_lines=2)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_trunc",
            artifact_path=Path("/repo/.worktree/sessions/sbx_trunc/diff.patch"),
            diff_text="line 1\nline 2\nline 3\nline 4\n",
            raw=False,
        )

        raw_output = formatter.to_raw(result)
        assert raw_output == "line 1\nline 2"

        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_trunc" in rendered
        assert "line 1" in rendered
        assert "line 2" in rendered
        assert "line 3" not in rendered
