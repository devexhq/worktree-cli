"""Tier 2 presentation contracts for DiffResultFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.diff import DiffResultFormatter, DiffResultView
from worktree.core.diff.models import DiffResult, DiffStatus

_SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass  # intentionally long line exceeding 120 characters to ensure diff raw output does not wrap at terminal columns boundaries
"""


def make_diff_view(**overrides: Any) -> DiffResultView:
    """Helper to construct a DiffResultView with healthy baseline defaults."""
    defaults: dict[str, Any] = {
        "status": DiffStatus.OK,
        "session_id": "sbx_fmt_1",
        "artifact_path": Path("/repo/.worktree/sessions/sbx_fmt_1/diff.patch"),
        "relative_path": "/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
        "diff_text": _SAMPLE_DIFF,
        "raw": False,
        "full": False,
        "max_lines": None,
        "total_lines": 6,
        "truncated": False,
        "truncated_lines": 0,
        "errors": [],
        "warnings": [],
        "fixes": [],
    }
    defaults.update(overrides)
    return DiffResultView(**defaults)


OK_POPULATED_DATA = DiffResult(
    status=DiffStatus.OK,
    session_id="sbx_fmt_1",
    artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_1/diff.patch"),
    diff_text=_SAMPLE_DIFF,
    warnings=["Non-critical warning"],
)
OK_POPULATED = FormatterCase(
    data=OK_POPULATED_DATA,
    view=make_diff_view(
        status=DiffStatus.OK,
        session_id="sbx_fmt_1",
        artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_1/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
        diff_text=_SAMPLE_DIFF,
        total_lines=6,
        warnings=["Non-critical warning"],
    ),
    render_expectations=[
        "sbx_fmt_1",
        "/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
        *(line.strip() for line in _SAMPLE_DIFF.splitlines()),
    ],
)

EMPTY_DIFF_DATA = DiffResult(
    status=DiffStatus.EMPTY_DIFF,
    session_id="sbx_fmt_empty",
    artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_empty/diff.patch"),
    diff_text="",
)
EMPTY_DIFF = FormatterCase(
    data=EMPTY_DIFF_DATA,
    view=make_diff_view(
        status=DiffStatus.EMPTY_DIFF,
        session_id="sbx_fmt_empty",
        artifact_path=Path("/repo/.worktree/sessions/sbx_fmt_empty/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_fmt_empty/diff.patch",
        diff_text="",
        total_lines=0,
    ),
    render_expectations=["sbx_fmt_empty", "No changes recorded"],
)

SESSION_NOT_FOUND_DATA = DiffResult(
    status=DiffStatus.SESSION_NOT_FOUND,
    session_id="sbx_missing_99",
    errors=["Session 'sbx_missing_99' not found under .worktree/sessions/."],
    fixes=["Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"],
)
SESSION_NOT_FOUND = FormatterCase(
    data=SESSION_NOT_FOUND_DATA,
    view=make_diff_view(
        status=DiffStatus.SESSION_NOT_FOUND,
        session_id="sbx_missing_99",
        artifact_path=None,
        relative_path=".worktree/sessions/sbx_missing_99/diff.patch",
        diff_text="",
        total_lines=0,
        errors=["Session 'sbx_missing_99' not found under .worktree/sessions/."],
        fixes=["Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"],
    ),
    render_expectations=["sbx_missing_99"],
)

NO_SESSIONS_DATA = DiffResult(
    status=DiffStatus.SESSION_NOT_FOUND,
    session_id=None,
    errors=["No loop run sessions found."],
)
NO_SESSIONS_FOUND = FormatterCase(
    data=NO_SESSIONS_DATA,
    view=make_diff_view(
        status=DiffStatus.SESSION_NOT_FOUND,
        session_id=None,
        artifact_path=None,
        relative_path=".worktree/sessions/<session_id>/diff.patch",
        diff_text="",
        total_lines=0,
        errors=["No loop run sessions found."],
    ),
    render_expectations=[],
)

DIFF_NOT_FOUND_DATA = DiffResult(
    status=DiffStatus.DIFF_NOT_FOUND,
    session_id="sbx_no_patch_artifact",
    errors=["Session 'sbx_no_patch_artifact' has no diff artifact."],
    fixes=["Verify the session generated a diff artifact at .worktree/sessions/sbx_no_patch_artifact/diff.patch"],
)
DIFF_NOT_FOUND = FormatterCase(
    data=DIFF_NOT_FOUND_DATA,
    view=make_diff_view(
        status=DiffStatus.DIFF_NOT_FOUND,
        session_id="sbx_no_patch_artifact",
        artifact_path=None,
        relative_path=".worktree/sessions/sbx_no_patch_artifact/diff.patch",
        diff_text="",
        total_lines=0,
        errors=["Session 'sbx_no_patch_artifact' has no diff artifact."],
        fixes=["Verify the session generated a diff artifact at .worktree/sessions/sbx_no_patch_artifact/diff.patch"],
    ),
    render_expectations=["sbx_no_patch_artifact"],
)

READ_FAILURE_DATA = DiffResult(
    status=DiffStatus.READ_FAILURE,
    session_id="sbx_corrupt",
    errors=["Failed to read diff artifact: Permission denied"],
    fixes=["Check file permissions and that the artifact is readable"],
)
READ_FAILURE = FormatterCase(
    data=READ_FAILURE_DATA,
    view=make_diff_view(
        status=DiffStatus.READ_FAILURE,
        session_id="sbx_corrupt",
        artifact_path=None,
        relative_path=".worktree/sessions/sbx_corrupt/diff.patch",
        diff_text="",
        total_lines=0,
        errors=["Failed to read diff artifact: Permission denied"],
        fixes=["Check file permissions and that the artifact is readable"],
    ),
    render_expectations=[],
)

RAW_DIFF_DATA = DiffResult(
    status=DiffStatus.OK,
    session_id="sbx_raw_1",
    artifact_path=Path("/repo/.worktree/sessions/sbx_raw_1/diff.patch"),
    diff_text=_SAMPLE_DIFF,
    raw=True,
)
RAW_DIFF = FormatterCase(
    data=RAW_DIFF_DATA,
    view=make_diff_view(
        status=DiffStatus.OK,
        session_id="sbx_raw_1",
        artifact_path=Path("/repo/.worktree/sessions/sbx_raw_1/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_raw_1/diff.patch",
        diff_text=_SAMPLE_DIFF,
        raw=True,
        total_lines=6,
    ),
    render_expectations=[],
)

DIFF_MAX_LINES_DATA = DiffResult(
    status=DiffStatus.OK,
    session_id="sbx_max_lines",
    artifact_path=Path("/repo/.worktree/sessions/sbx_max_lines/diff.patch"),
    diff_text=_SAMPLE_DIFF,
    max_lines=10,
)
DIFF_WITH_MAX_LINES = FormatterCase(
    data=DIFF_MAX_LINES_DATA,
    view=make_diff_view(
        status=DiffStatus.OK,
        session_id="sbx_max_lines",
        artifact_path=Path("/repo/.worktree/sessions/sbx_max_lines/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_max_lines/diff.patch",
        diff_text=_SAMPLE_DIFF,
        max_lines=10,
        total_lines=6,
    ),
    render_expectations=[
        "sbx_max_lines",
        "/repo/.worktree/sessions/sbx_max_lines/diff.patch",
        *(line.strip() for line in _SAMPLE_DIFF.splitlines()),
    ],
)

DIFF_FULL_DATA = DiffResult(
    status=DiffStatus.OK,
    session_id="sbx_full",
    artifact_path=Path("/repo/.worktree/sessions/sbx_full/diff.patch"),
    diff_text=_SAMPLE_DIFF,
    full=True,
)
DIFF_FULL_FLAG = FormatterCase(
    data=DIFF_FULL_DATA,
    view=make_diff_view(
        status=DiffStatus.OK,
        session_id="sbx_full",
        artifact_path=Path("/repo/.worktree/sessions/sbx_full/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_full/diff.patch",
        diff_text=_SAMPLE_DIFF,
        full=True,
        total_lines=6,
    ),
    render_expectations=[
        "sbx_full",
        "/repo/.worktree/sessions/sbx_full/diff.patch",
        *(line.strip() for line in _SAMPLE_DIFF.splitlines()),
    ],
)

GENERAL_ERROR_DATA = DiffResult(
    status=DiffStatus.SESSION_NOT_FOUND,
    errors=["Unexpected internal failure"],
)
GENERAL_ERROR = FormatterCase(
    data=GENERAL_ERROR_DATA,
    view=make_diff_view(
        status=DiffStatus.SESSION_NOT_FOUND,
        session_id=None,
        artifact_path=None,
        relative_path=".worktree/sessions/<session_id>/diff.patch",
        diff_text="",
        total_lines=0,
        errors=["Unexpected internal failure"],
    ),
    render_expectations=[],
)

DIFF_TRUNCATED_TRUE_DATA = DiffResult(
    status=DiffStatus.OK,
    session_id="sbx_truncated_true",
    artifact_path=Path("/repo/.worktree/sessions/sbx_truncated_true/diff.patch"),
    diff_text=_SAMPLE_DIFF,
    max_lines=2,
)
DIFF_WITH_TRUNCATED_TRUE = FormatterCase(
    data=DIFF_TRUNCATED_TRUE_DATA,
    view=make_diff_view(
        status=DiffStatus.OK,
        session_id="sbx_truncated_true",
        artifact_path=Path("/repo/.worktree/sessions/sbx_truncated_true/diff.patch"),
        relative_path="/repo/.worktree/sessions/sbx_truncated_true/diff.patch",
        diff_text=_SAMPLE_DIFF,
        max_lines=2,
        total_lines=6,
        truncated=True,
        truncated_lines=2,
    ),
    render_expectations=[
        "sbx_truncated_true",
        "/repo/.worktree/sessions/sbx_truncated_true/diff.patch",
        "2",
        "6",
    ],
)


DIFF_CASES = [
    pytest.param(OK_POPULATED, id="ok_populated_diff"),
    pytest.param(EMPTY_DIFF, id="empty_diff"),
    pytest.param(SESSION_NOT_FOUND, id="session_not_found"),
    pytest.param(NO_SESSIONS_FOUND, id="no_sessions_found"),
    pytest.param(DIFF_NOT_FOUND, id="diff_not_found"),
    pytest.param(READ_FAILURE, id="read_failure"),
    pytest.param(RAW_DIFF, id="raw_diff"),
    pytest.param(DIFF_WITH_MAX_LINES, id="diff_with_max_lines"),
    pytest.param(DIFF_FULL_FLAG, id="diff_full_flag"),
    pytest.param(GENERAL_ERROR, id="general_error"),
    pytest.param(DIFF_WITH_TRUNCATED_TRUE, id="diff_with_truncated_true"),
]

DIFF_PAYLOAD_CASES = [
    pytest.param(
        OK_POPULATED,
        {
            "status": "ok",
            "session_id": "sbx_fmt_1",
            "artifact_path": "/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
            "relative_path": "/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
            "diff_text": _SAMPLE_DIFF,
            "raw": False,
            "full": False,
            "max_lines": None,
            "total_lines": 6,
            "truncated": False,
            "truncated_lines": 0,
            "errors": [],
            "warnings": ["Non-critical warning"],
            "fixes": [],
        },
        id="ok_populated_diff",
    ),
    pytest.param(
        EMPTY_DIFF,
        {
            "status": "empty_diff",
            "session_id": "sbx_fmt_empty",
            "artifact_path": "/repo/.worktree/sessions/sbx_fmt_empty/diff.patch",
            "relative_path": "/repo/.worktree/sessions/sbx_fmt_empty/diff.patch",
            "diff_text": "",
            "raw": False,
            "full": False,
            "max_lines": None,
            "total_lines": 0,
            "truncated": False,
            "truncated_lines": 0,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="empty_diff",
    ),
    pytest.param(
        SESSION_NOT_FOUND,
        {
            "status": "session_not_found",
            "session_id": "sbx_missing_99",
            "artifact_path": None,
            "relative_path": ".worktree/sessions/sbx_missing_99/diff.patch",
            "diff_text": "",
            "raw": False,
            "full": False,
            "max_lines": None,
            "total_lines": 0,
            "truncated": False,
            "truncated_lines": 0,
            "errors": ["Session 'sbx_missing_99' not found under .worktree/sessions/."],
            "warnings": [],
            "fixes": ["Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"],
        },
        id="session_not_found",
    ),
]


class DiffResultFormatterTests:
    """Tier 2 presentation contract tests for DiffResultFormatter."""

    @pytest.mark.parametrize("case", DIFF_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[DiffResult, DiffResultView]) -> None:
        """Verify transform derives the exact DiffResultView model representation."""
        formatter = DiffResultFormatter(console=Console(force_terminal=True))
        assert formatter.transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), DIFF_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[DiffResult, DiffResultView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert DiffResultFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", DIFF_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[DiffResult, DiffResultView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        formatter = DiffResultFormatter(console=Console(force_terminal=True))
        rendered = render_rich(formatter.to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
        for error in case.view.errors:
            assert error in rendered
        for fix in case.view.fixes:
            assert fix in rendered

    def test_transform_when_non_terminal_bypasses_truncation(self) -> None:
        formatter = DiffResultFormatter(console=Console(force_terminal=False))
        view = formatter.transform(DIFF_TRUNCATED_TRUE_DATA)
        assert view.truncated is False
        assert view.truncated_lines == 0

    def test_to_raw_when_raw_returns_diff_text(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_raw_1",
            artifact_path=Path("/repo/.worktree/sessions/sbx_raw_1/diff.patch"),
            diff_text=_SAMPLE_DIFF,
            raw=True,
        )
        assert formatter.to_raw(result) == _SAMPLE_DIFF

    def test_to_raw_when_empty_diff_renders_notice(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.EMPTY_DIFF,
            session_id="sbx_raw_empty",
            artifact_path=Path("/repo/.worktree/sessions/sbx_raw_empty/diff.patch"),
            diff_text="",
        )
        assert formatter.to_raw(result) == "No changes recorded for session sbx_raw_empty."

    def test_to_raw_when_session_not_found_renders_error(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            session_id="sbx_missing_raw",
            errors=["Session 'sbx_missing_raw' not found under .worktree/sessions/."],
        )
        raw_output = formatter.to_raw(result)
        assert "Session 'sbx_missing_raw' not found" in raw_output

    def test_to_raw_when_unclassified_error_renders_error(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.OK,
            errors=["Generic diff failure"],
        )
        raw_output = formatter.to_raw(result)
        assert "Generic diff failure" in raw_output

    def test_to_raw_when_terminal_truncates_lines(self) -> None:
        formatter = DiffResultFormatter(console=Console(force_terminal=True), max_lines=2)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_trunc",
            artifact_path=Path("/repo/.worktree/sessions/sbx_trunc/diff.patch"),
            diff_text="line 1\nline 2\nline 3\nline 4\n",
            raw=False,
        )
        assert formatter.to_raw(result) == "line 1\nline 2"

    def test_to_raw_when_full_bypasses_truncation(self) -> None:
        formatter = DiffResultFormatter(console=Console(force_terminal=True), max_lines=2, full=True)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_trunc",
            artifact_path=Path("/repo/.worktree/sessions/sbx_trunc/diff.patch"),
            diff_text="line 1\nline 2\nline 3\nline 4\n",
            raw=False,
        )
        assert formatter.to_raw(result) == "line 1\nline 2\nline 3\nline 4\n"

    def test_to_raw_when_non_terminal_bypasses_truncation(self) -> None:
        formatter = DiffResultFormatter(console=Console(force_terminal=False), max_lines=2)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_trunc",
            artifact_path=Path("/repo/.worktree/sessions/sbx_trunc/diff.patch"),
            diff_text="line 1\nline 2\nline 3\nline 4\n",
            raw=False,
        )
        assert formatter.to_raw(result) == "line 1\nline 2\nline 3\nline 4\n"
