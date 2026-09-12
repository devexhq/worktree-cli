"""Tier 2 presentation contract tests for SandboxShowFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_show import SandboxShowFormatter
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    SandboxShowResult,
    SandboxShowStatus,
)

_RECORD = SandboxRecord(
    id="sbx_test1234",
    name="test-sandbox",
    branch_name="worktree/sandbox-test",
    base_commit="abc1234",
    sandbox_path="/tmp/sbx_test1234",
    status=SandboxStatus.ACTIVE,
    created_at="2026-08-31T20:00:00Z",
    updated_at="2026-08-31T20:00:00Z",
)

FOUND_ACTIVE = FormatterCase(
    data=SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=_RECORD,
        disk_present=True,
    ),
    view=SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=_RECORD,
        disk_present=True,
    ),
    render_expectations=[_RECORD.id, "test-sandbox", _RECORD.branch_name, _RECORD.base_commit],
)

RECONCILED_MISSING_DISK = FormatterCase(
    data=SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=_RECORD,
        disk_present=False,
        reconciled=True,
    ),
    view=SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=_RECORD,
        disk_present=False,
        reconciled=True,
    ),
    render_expectations=[_RECORD.id, "test-sandbox", _RECORD.branch_name, _RECORD.base_commit],
)

NOT_FOUND = FormatterCase(
    data=SandboxShowResult(
        status=SandboxShowStatus.NOT_FOUND,
        errors=["Sandbox 'sbx_missing' not found."],
        fixes=["Run `wt sandbox list` to see known sandboxes"],
    ),
    view=SandboxShowResult(
        status=SandboxShowStatus.NOT_FOUND,
        errors=["Sandbox 'sbx_missing' not found."],
        fixes=["Run `wt sandbox list` to see known sandboxes"],
    ),
    render_expectations=[],
)

SANDBOX_SHOW_CASES = [
    pytest.param(FOUND_ACTIVE, id="found_active"),
    pytest.param(RECONCILED_MISSING_DISK, id="reconciled_missing_disk"),
    pytest.param(NOT_FOUND, id="not_found"),
]

SANDBOX_SHOW_PAYLOAD_CASES = [
    pytest.param(
        FOUND_ACTIVE,
        {
            "status": "ok",
            "sandbox": {
                "id": "sbx_test1234",
                "name": "test-sandbox",
                "branch_name": "worktree/sandbox-test",
                "base_commit": "abc1234",
                "sandbox_path": "/tmp/sbx_test1234",
                "status": "active",
                "created_at": "2026-08-31T20:00:00Z",
                "updated_at": "2026-08-31T20:00:00Z",
            },
            "disk_present": True,
            "reconciled": False,
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="found_active",
    ),
    pytest.param(
        RECONCILED_MISSING_DISK,
        {
            "status": "ok",
            "sandbox": {
                "id": "sbx_test1234",
                "name": "test-sandbox",
                "branch_name": "worktree/sandbox-test",
                "base_commit": "abc1234",
                "sandbox_path": "/tmp/sbx_test1234",
                "status": "active",
                "created_at": "2026-08-31T20:00:00Z",
                "updated_at": "2026-08-31T20:00:00Z",
            },
            "disk_present": False,
            "reconciled": True,
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="reconciled_missing_disk",
    ),
    pytest.param(
        NOT_FOUND,
        {
            "status": "not_found",
            "sandbox": None,
            "disk_present": False,
            "reconciled": False,
            "warnings": [],
            "errors": ["Sandbox 'sbx_missing' not found."],
            "fixes": ["Run `wt sandbox list` to see known sandboxes"],
        },
        id="not_found",
    ),
]


class SandboxShowFormatterTests:
    """Tier 2 presentation contract tests for SandboxShowFormatter."""

    @pytest.mark.parametrize("case", SANDBOX_SHOW_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[SandboxShowResult, SandboxShowResult]) -> None:
        """Verify transform derives the identity view representation."""
        assert SandboxShowFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), SANDBOX_SHOW_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[SandboxShowResult, SandboxShowResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert SandboxShowFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", SANDBOX_SHOW_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[SandboxShowResult, SandboxShowResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(SandboxShowFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered
