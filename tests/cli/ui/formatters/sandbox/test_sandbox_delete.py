"""Tier 2 presentation contract tests for SandboxDeleteFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_delete import SandboxDeleteFormatter
from worktree.core.sandbox.models import (
    SandboxDeleteResult,
    SandboxDeleteStatus,
)

DELETED = FormatterCase(
    data=SandboxDeleteResult(
        status=SandboxDeleteStatus.DELETED,
        sandbox_id="sbx_del",
        deleted=True,
    ),
    view=SandboxDeleteResult(
        status=SandboxDeleteStatus.DELETED,
        sandbox_id="sbx_del",
        deleted=True,
    ),
    render_expectations=["sbx_del"],
)

ALREADY_CLEANED = FormatterCase(
    data=SandboxDeleteResult(
        status=SandboxDeleteStatus.ALREADY_CLEANED,
        sandbox_id="sbx_del",
        deleted=False,
    ),
    view=SandboxDeleteResult(
        status=SandboxDeleteStatus.ALREADY_CLEANED,
        sandbox_id="sbx_del",
        deleted=False,
    ),
    render_expectations=["sbx_del"],
)

ABORTED = FormatterCase(
    data=SandboxDeleteResult(
        status=SandboxDeleteStatus.ABORTED,
        sandbox_id="sbx_del",
        deleted=False,
    ),
    view=SandboxDeleteResult(
        status=SandboxDeleteStatus.ABORTED,
        sandbox_id="sbx_del",
        deleted=False,
    ),
    render_expectations=[],
)

NOT_FOUND = FormatterCase(
    data=SandboxDeleteResult(
        status=SandboxDeleteStatus.NOT_FOUND,
        sandbox_id="sbx_missing",
        deleted=False,
        errors=["Sandbox 'sbx_missing' not found."],
        fixes=["Run `wt sandbox list` to see known sandboxes"],
    ),
    view=SandboxDeleteResult(
        status=SandboxDeleteStatus.NOT_FOUND,
        sandbox_id="sbx_missing",
        deleted=False,
        errors=["Sandbox 'sbx_missing' not found."],
        fixes=["Run `wt sandbox list` to see known sandboxes"],
    ),
    render_expectations=["sbx_missing"],
)

SANDBOX_DELETE_CASES = [
    pytest.param(DELETED, id="deleted"),
    pytest.param(ALREADY_CLEANED, id="already_cleaned"),
    pytest.param(ABORTED, id="aborted"),
    pytest.param(NOT_FOUND, id="not_found"),
]

SANDBOX_DELETE_PAYLOAD_CASES = [
    pytest.param(
        DELETED,
        {
            "status": "deleted",
            "sandbox_id": "sbx_del",
            "sandbox": None,
            "deleted": True,
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="deleted",
    ),
    pytest.param(
        ALREADY_CLEANED,
        {
            "status": "already_cleaned",
            "sandbox_id": "sbx_del",
            "sandbox": None,
            "deleted": False,
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="already_cleaned",
    ),
    pytest.param(
        ABORTED,
        {
            "status": "aborted",
            "sandbox_id": "sbx_del",
            "sandbox": None,
            "deleted": False,
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="aborted",
    ),
    pytest.param(
        NOT_FOUND,
        {
            "status": "not_found",
            "sandbox_id": "sbx_missing",
            "sandbox": None,
            "deleted": False,
            "warnings": [],
            "errors": ["Sandbox 'sbx_missing' not found."],
            "fixes": ["Run `wt sandbox list` to see known sandboxes"],
        },
        id="not_found",
    ),
]


class SandboxDeleteFormatterTests:
    """Tier 2 presentation contract tests for SandboxDeleteFormatter."""

    @pytest.mark.parametrize("case", SANDBOX_DELETE_CASES)
    def test_transform_derives_expected_view(
        self, case: FormatterCase[SandboxDeleteResult, SandboxDeleteResult]
    ) -> None:
        """Verify transform derives the identity view representation."""
        assert SandboxDeleteFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), SANDBOX_DELETE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[SandboxDeleteResult, SandboxDeleteResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert SandboxDeleteFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", SANDBOX_DELETE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[SandboxDeleteResult, SandboxDeleteResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(SandboxDeleteFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered
