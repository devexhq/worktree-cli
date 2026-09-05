"""Tier 2 presentation contract tests for SandboxShowFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_show import SandboxShowFormatter
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    SandboxShowResult,
    SandboxShowStatus,
)


class SandboxShowFormatterTests:
    """Presentation contract tests for SandboxShowFormatter."""

    def test_to_rich_found_contains_sandbox_id(self) -> None:
        formatter = SandboxShowFormatter()
        record = SandboxRecord(
            id="sbx_test1234",
            name="test-sandbox",
            branch_name="worktree/sandbox-test",
            base_commit="abc1234",
            sandbox_path="/tmp/sbx_test1234",
            status=SandboxStatus.ACTIVE,
            created_at="2026-08-31T20:00:00Z",
            updated_at="2026-08-31T20:00:00Z",
        )
        result = SandboxShowResult(
            status=SandboxShowStatus.OK,
            sandbox=record,
            disk_present=True,
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_test1234" in rendered

    def test_to_rich_not_found_contains_error_message(self) -> None:
        formatter = SandboxShowFormatter()
        not_found_result = SandboxShowResult(
            status=SandboxShowStatus.NOT_FOUND,
            errors=["Sandbox 'sbx_missing' not found."],
        )
        rendered_missing = render_rich(formatter.to_rich(not_found_result))
        assert "sbx_missing" in rendered_missing

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxShowFormatter()
        record = SandboxRecord(
            id="sbx_test1234",
            name="test-sandbox",
            branch_name="worktree/sandbox-test",
            base_commit="abc1234",
            sandbox_path="/tmp/sbx_test1234",
            status=SandboxStatus.ACTIVE,
            created_at="2026-08-31T20:00:00Z",
            updated_at="2026-08-31T20:00:00Z",
        )
        result = SandboxShowResult(
            status=SandboxShowStatus.OK,
            sandbox=record,
            disk_present=True,
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
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
        }
