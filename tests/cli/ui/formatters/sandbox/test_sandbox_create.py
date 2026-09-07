"""Tier 2 presentation contract tests for SandboxCreateFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_create import SandboxCreateFormatter
from worktree.core.sandbox.models import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)

_SESSION = SandboxSession(
    session_id="sbx_create123",
    target_branch="worktree/sandbox-create123",
    sandbox_path=Path("/tmp/sbx_create123"),
    base_commit="def5678",
    created_at="2026-08-31T20:00:00Z",
)

CREATED_OK = FormatterCase(
    data=SandboxCreateResult(status=SandboxCreateStatus.OK, session=_SESSION),
    view=SandboxCreateResult(status=SandboxCreateStatus.OK, session=_SESSION),
    render_expectations=[_SESSION.session_id, _SESSION.target_branch],
)

FAILED_GIT = FormatterCase(
    data=SandboxCreateResult(
        status=SandboxCreateStatus.GIT_FAILED,
        errors=["Git checkout failed."],
        fixes=["Check git status and branch name"],
    ),
    view=SandboxCreateResult(
        status=SandboxCreateStatus.GIT_FAILED,
        errors=["Git checkout failed."],
        fixes=["Check git status and branch name"],
    ),
    render_expectations=[],
)

SANDBOX_CREATE_CASES = [
    pytest.param(CREATED_OK, id="created_ok"),
    pytest.param(FAILED_GIT, id="failed_git"),
]

SANDBOX_CREATE_PAYLOAD_CASES = [
    pytest.param(
        CREATED_OK,
        {
            "status": "ok",
            "session": {
                "session_id": "sbx_create123",
                "target_branch": "worktree/sandbox-create123",
                "sandbox_path": "/tmp/sbx_create123",
                "base_commit": "def5678",
                "name": None,
                "created_at": "2026-08-31T20:00:00Z",
                "command_passed": None,
                "wip_applied": False,
                "wip_paths": [],
            },
            "warnings": [],
            "errors": [],
            "fixes": [],
        },
        id="created_ok",
    ),
    pytest.param(
        FAILED_GIT,
        {
            "status": "git_failed",
            "session": None,
            "warnings": [],
            "errors": ["Git checkout failed."],
            "fixes": ["Check git status and branch name"],
        },
        id="failed_git",
    ),
]


class SandboxCreateFormatterTests:
    """Tier 2 presentation contract tests for SandboxCreateFormatter."""

    @pytest.mark.parametrize("case", SANDBOX_CREATE_CASES)
    def test_transform_derives_expected_view(
        self, case: FormatterCase[SandboxCreateResult, SandboxCreateResult]
    ) -> None:
        """Verify transform derives the identity view representation."""
        assert SandboxCreateFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), SANDBOX_CREATE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[SandboxCreateResult, SandboxCreateResult],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert SandboxCreateFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", SANDBOX_CREATE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[SandboxCreateResult, SandboxCreateResult]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(SandboxCreateFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for error in view.errors:
            assert error in rendered

        for fix in view.fixes:
            assert fix in rendered

        for warning in view.warnings:
            assert warning in rendered
