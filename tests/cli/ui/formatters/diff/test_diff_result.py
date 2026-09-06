"""Tier 2 presentation contracts for DiffResultFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.diff import DiffResultFormatter, DiffResultView
from worktree.cli.ui.formatters.diff.common import resolve_diff_rel_path
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
        relative_path=resolve_diff_rel_path(OK_POPULATED_DATA),
        diff_text=_SAMPLE_DIFF,
        total_lines=6,
        warnings=["Non-critical warning"],
    ),
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
        relative_path=resolve_diff_rel_path(EMPTY_DIFF_DATA),
        diff_text="",
        total_lines=0,
    ),
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
        relative_path=resolve_diff_rel_path(RAW_DIFF_DATA),
        diff_text=_SAMPLE_DIFF,
        raw=True,
        total_lines=6,
    ),
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
        relative_path=resolve_diff_rel_path(DIFF_MAX_LINES_DATA),
        diff_text=_SAMPLE_DIFF,
        max_lines=10,
        total_lines=6,
    ),
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
        relative_path=resolve_diff_rel_path(DIFF_FULL_DATA),
        diff_text=_SAMPLE_DIFF,
        full=True,
        total_lines=6,
    ),
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
]

DIFF_PAYLOAD_CASES = [
    pytest.param(
        OK_POPULATED,
        {
            "status": "ok",
            "session_id": "sbx_fmt_1",
            "artifact_path": "/repo/.worktree/sessions/sbx_fmt_1/diff.patch",
            "relative_path": resolve_diff_rel_path(OK_POPULATED_DATA),
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
            "relative_path": resolve_diff_rel_path(EMPTY_DIFF_DATA),
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


def _assert_rendered_session_and_messages(rendered: str, view: DiffResultView) -> None:
    """Assert session ID, error messages, and remediation hints reach rendered text."""
    if view.session_id is not None and not view.raw and view.status != DiffStatus.READ_FAILURE:
        assert view.session_id in rendered
    for error in view.errors:
        assert error in rendered
    for fix in view.fixes:
        assert fix in rendered


def _assert_rendered_diff_content(rendered: str, view: DiffResultView) -> None:
    """Assert relative path, patch lines, and empty diff notices reach rendered text."""
    if view.status == DiffStatus.OK and not view.raw and view.relative_path:
        assert view.relative_path in rendered
    if view.status == DiffStatus.OK and view.diff_text and not view.truncated:
        for line in view.diff_text.splitlines():
            assert line.strip() in rendered
    if view.status == DiffStatus.EMPTY_DIFF:
        assert "No changes recorded" in rendered


class DiffResultFormatterTests:
    """Tier 2 presentation contract tests for DiffResultFormatter."""

    @pytest.mark.parametrize("case", DIFF_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[DiffResult, DiffResultView]) -> None:
        """Verify transform derives the exact DiffResultView model representation."""
        assert DiffResultFormatter().transform(case.data) == case.view

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
        rendered = render_rich(DiffResultFormatter().to_rich(case.data))
        _assert_rendered_session_and_messages(rendered, case.view)
        _assert_rendered_diff_content(rendered, case.view)
