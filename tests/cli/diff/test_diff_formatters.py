"""Unit tests for DiffResultFormatter and diff UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.diff import (
    DiffResultFormatter,
    register_diff_formatters,
)
from worktree.core.diff.models import DiffResult, DiffStatus

_SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass  # intentionally long line exceeding 120 characters to ensure diff raw output does not wrap at terminal columns boundaries
"""


def test_diff_result_formatter_to_rich_success() -> None:
    """Verify to_rich renders session header and syntax-highlighted diff on success."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_fmt_1",
        artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_1/diff.patch"),
        diff_text=_SAMPLE_DIFF,
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    out = render_rich(rich_renderable)
    assert "Session: sbx_fmt_1" in out
    assert "def old(): pass" in out
    assert "def new(): pass" in out


def test_diff_result_formatter_to_rich_empty_diff() -> None:
    """Verify to_rich renders single-line message for empty diff."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.EMPTY_DIFF,
        session_id="sbx_fmt_empty",
        artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_empty/diff.patch"),
        diff_text="",
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Text)

    out = render_rich(rich_renderable)
    assert "No changes recorded for session sbx_fmt_empty." in out


def test_diff_result_formatter_to_rich_session_not_found_explicit() -> None:
    """Verify to_rich renders Session Not Found panel with explicit session ID."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.SESSION_NOT_FOUND,
        session_id="sbx_missing_99",
        errors=["Session 'sbx_missing_99' not found under .worktree/sessions/."],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    out = render_rich(rich_renderable)
    assert "Session Not Found" in out
    assert "Session 'sbx_missing_99' not found under .worktree/sessions/." in out
    assert "Run `wt sandbox list`" in out


def test_diff_result_formatter_to_rich_session_not_found_implicit() -> None:
    """Verify to_rich renders Session Not Found panel when no sessions exist."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.SESSION_NOT_FOUND,
        errors=["No loop run sessions found."],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    out = render_rich(rich_renderable)
    assert "Session Not Found" in out
    assert "No loop run sessions found." in out


def test_diff_result_formatter_to_rich_diff_not_found() -> None:
    """Verify to_rich renders Diff Not Found panel when diff artifact is missing."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.DIFF_NOT_FOUND,
        session_id="sbx_no_patch_artifact",
        errors=["Session 'sbx_no_patch_artifact' has no diff artifact."],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    out = render_rich(rich_renderable)
    assert "Diff Not Found" in out
    assert "Session 'sbx_no_patch_artifact' has no diff artifact." in out


def test_diff_result_formatter_to_rich_read_failure() -> None:
    """Verify to_rich renders Read Failure panel on OSError."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.READ_FAILURE,
        session_id="sbx_corrupt",
        errors=["Failed to read diff artifact at '...': Permission denied"],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    out = render_rich(rich_renderable)
    assert "Read Failure" in out
    assert "Permission denied" in out


def test_diff_result_formatter_to_rich_general_error() -> None:
    """Verify to_rich renders Diff Failed panel on general errors."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.SESSION_NOT_FOUND,
        errors=["Unexpected internal failure"],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    out = render_rich(rich_renderable)
    assert "Session Not Found" in out


def test_diff_result_formatter_to_json_serializable() -> None:
    """Verify to_json_serializable returns a dictionary matching model_dump."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_json_1",
        artifact_path=Path("/tmp/diff.patch"),
        diff_text=_SAMPLE_DIFF,
        warnings=["Non-critical warning"],
    )

    dumped = formatter.to_json_serializable(result)
    assert isinstance(dumped, dict)
    assert dumped["status"] == "ok"
    assert dumped["session_id"] == "sbx_json_1"
    assert dumped["artifact_path"] == "/tmp/diff.patch"
    assert dumped["diff_text"] == _SAMPLE_DIFF
    assert dumped["warnings"] == ["Non-critical warning"]
    assert dumped["errors"] == []

    # Verify JSON encoding works without errors
    encoded = json.dumps(dumped)
    decoded = json.loads(encoded)
    assert decoded["session_id"] == "sbx_json_1"


def test_register_diff_formatters_custom_dispatcher() -> None:
    """Verify registering on custom UiDispatcher instance."""
    dispatcher = UiDispatcher()
    register_diff_formatters(dispatcher)

    assert DiffResult in dispatcher._registry
    assert isinstance(dispatcher._registry[DiffResult], DiffResultFormatter)


def test_ui_dispatcher_registration() -> None:
    """Verify central ui_dispatcher has DiffResultFormatter registered."""
    assert DiffResult in ui_dispatcher._registry
    assert isinstance(ui_dispatcher._registry[DiffResult], DiffResultFormatter)


def test_dispatcher_json_format_ndjson(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify dispatcher outputs structured NDJSON envelope in json mode."""
    dispatcher = UiDispatcher()
    register_diff_formatters(dispatcher)
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_ndjson",
        artifact_path=Path("/repo/.worktree/sessions/sbx_ndjson/diff.patch"),
        diff_text=_SAMPLE_DIFF,
    )

    dispatcher.dispatch(result, output_format="json")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event_type"] == "DiffResult"
    assert payload["payload"]["status"] == "ok"
    assert payload["payload"]["session_id"] == "sbx_ndjson"
    assert payload["payload"]["diff_text"] == _SAMPLE_DIFF


def test_dispatcher_terminal_format() -> None:
    """Verify dispatcher prints formatted console text in terminal mode."""
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_term",
        artifact_path=Path("/repo/.worktree/sessions/sbx_term/diff.patch"),
        diff_text=_SAMPLE_DIFF,
    )

    dispatcher.dispatch(result, output_format="terminal")

    output = buffer.getvalue()
    assert "Session: sbx_term" in output
    assert "def old(): pass" in output


def test_diff_result_formatter_to_raw_exact_unwrapped() -> None:
    """Verify to_raw returns exact diff_text without wrapping lines over 120 chars when raw=True."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_raw_1",
        artifact_path=Path("/repo/.worktree/sessions/sbx_raw_1/diff.patch"),
        diff_text=_SAMPLE_DIFF,
        raw=True,
    )

    out = formatter.to_raw(result)
    assert out == _SAMPLE_DIFF


def test_diff_result_formatter_to_raw_empty_diff() -> None:
    """Verify to_raw returns single-line message for empty diff."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.EMPTY_DIFF,
        session_id="sbx_raw_empty",
        artifact_path=Path("/repo/.worktree/sessions/sbx_raw_empty/diff.patch"),
        diff_text="",
    )

    out = formatter.to_raw(result)
    assert out == "No changes recorded for session sbx_raw_empty."


def test_diff_result_formatter_to_raw_error_panel() -> None:
    """Verify to_raw returns raw string error panel on non-ok status."""
    formatter = DiffResultFormatter()
    result = DiffResult(
        status=DiffStatus.SESSION_NOT_FOUND,
        session_id="sbx_missing_raw",
        errors=["Session 'sbx_missing_raw' not found under .worktree/sessions/."],
    )

    out = formatter.to_raw(result)
    assert "Session 'sbx_missing_raw' not found" in out


def test_diff_result_formatter_injected_console_tty_truncation() -> None:
    """Verify injected Console with is_terminal=True enables truncation in to_raw and to_rich."""
    forced_tty_console = Console(force_terminal=True)
    formatter = DiffResultFormatter(console=forced_tty_console, max_lines=2)
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_trunc",
        artifact_path=Path("/repo/.worktree/sessions/sbx_trunc/diff.patch"),
        diff_text="line 1\nline 2\nline 3\nline 4\n",
        raw=False,
    )

    # to_raw truncates to max_lines when running under TTY and raw=False
    raw_out = formatter.to_raw(result)
    assert raw_out == "line 1\nline 2"

    # to_rich renders truncation notice
    rich_out = render_rich(formatter.to_rich(result))
    assert "diff truncated: showing 2 of 4 lines" in rich_out


def test_dispatcher_raw_format(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify dispatcher prints exact raw text without wrapping in raw mode."""
    dispatcher = UiDispatcher()
    register_diff_formatters(dispatcher)
    result = DiffResult(
        status=DiffStatus.OK,
        session_id="sbx_raw_dispatch",
        artifact_path=Path("/repo/.worktree/sessions/sbx_raw_dispatch/diff.patch"),
        diff_text=_SAMPLE_DIFF,
        raw=True,
    )

    dispatcher.dispatch(result, output_format="raw")

    captured = capsys.readouterr()
    assert captured.out == _SAMPLE_DIFF
