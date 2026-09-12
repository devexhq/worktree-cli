"""Tier 2 presentation contract tests for SandboxListFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_list import SandboxListFormatter
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    SandboxListResult,
    SandboxListStatus,
)

_RECORD = SandboxRecord(
    id="sbx_list1234",
    name="list-sandbox",
    branch_name="worktree/sandbox-list",
    base_commit="abc1234",
    sandbox_path="/tmp/sbx_list1234",
    status=SandboxStatus.ACTIVE,
    created_at="2026-08-31T20:00:00Z",
    updated_at="2026-08-31T20:00:00Z",
)

WITH_SANDBOXES = FormatterCase(
    data=SandboxListResult(status=SandboxListStatus.OK, sandboxes=[_RECORD]),
    view=SandboxListResult(status=SandboxListStatus.OK, sandboxes=[_RECORD]),
    render_expectations=[_RECORD.id, "list-sandbox", _RECORD.branch_name],
)

EMPTY_SANDBOXES = FormatterCase(
    data=SandboxListResult(status=SandboxListStatus.OK, sandboxes=[]),
    view=SandboxListResult(status=SandboxListStatus.OK, sandboxes=[]),
    render_expectations=[],
)

NOT_INITIALIZED = FormatterCase(
    data=SandboxListResult(
        status=SandboxListStatus.NOT_INITIALIZED,
        sandboxes=[],
        errors=["Worktree workspace is not initialized."],
        fixes=["Run `wt init` to create `.worktree/config.json`"],
    ),
    view=SandboxListResult(
        status=SandboxListStatus.NOT_INITIALIZED,
        sandboxes=[],
        errors=["Worktree workspace is not initialized."],
        fixes=["Run `wt init` to create `.worktree/config.json`"],
    ),
    render_expectations=[],
)

SANDBOX_LIST_CASES = [
    pytest.param(WITH_SANDBOXES, id="with_sandboxes"),
    pytest.param(EMPTY_SANDBOXES, id="empty_sandboxes"),
    pytest.param(NOT_INITIALIZED, id="not_initialized"),
]

SANDBOX_LIST_PAYLOAD_CASES = [
    pytest.param(
        WITH_SANDBOXES,
        {
            "status": "ok",
            "sandboxes": [
                {
                    "id": "sbx_list1234",
                    "name": "list-sandbox",
                    "branch_name": "worktree/sandbox-list",
                    "base_commit": "abc1234",
                    "sandbox_path": "/tmp/sbx_list1234",
                    "status": "active",
                    "created_at": "2026-08-31T20:00:00Z",
                    "updated_at": "2026-08-31T20:00:00Z",
                }
            ],
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="with_sandboxes",
    ),
    pytest.param(
        EMPTY_SANDBOXES,
        {
            "status": "ok",
            "sandboxes": [],
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="empty_sandboxes",
    ),
    pytest.param(
        NOT_INITIALIZED,
        {
            "status": "not_initialized",
            "sandboxes": [],
            "warnings": [],
            "errors": ["Worktree workspace is not initialized."],
            "fixes": ["Run `wt init` to create `.worktree/config.json`"],
        },
        id="not_initialized",
    ),
]


class SandboxListFormatterTests:
    """Tier 2 presentation contract tests for SandboxListFormatter."""

    @pytest.mark.parametrize("case", SANDBOX_LIST_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[SandboxListResult, SandboxListResult]) -> None:
        """Verify transform derives the identity view representation."""
        assert SandboxListFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), SANDBOX_LIST_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[SandboxListResult, SandboxListResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert SandboxListFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", SANDBOX_LIST_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[SandboxListResult, SandboxListResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(SandboxListFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered
