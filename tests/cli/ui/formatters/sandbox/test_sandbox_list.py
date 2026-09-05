"""Tier 2 presentation contract tests for SandboxListFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_list import SandboxListFormatter
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    SandboxListResult,
    SandboxListStatus,
)


class SandboxListFormatterTests:
    """Presentation contract tests for SandboxListFormatter."""

    def test_to_rich_with_items_contains_sandbox_id(self) -> None:
        formatter = SandboxListFormatter()
        record = SandboxRecord(
            id="sbx_list1234",
            name="list-sandbox",
            branch_name="worktree/sandbox-list",
            base_commit="abc1234",
            sandbox_path="/tmp/sbx_list1234",
            status=SandboxStatus.ACTIVE,
            created_at="2026-08-31T20:00:00Z",
            updated_at="2026-08-31T20:00:00Z",
        )
        result_items = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[record])
        rendered_items = render_rich(formatter.to_rich(result_items))
        assert "sbx_list1234" in rendered_items

    def test_to_rich_when_empty_omits_sandboxes(self) -> None:
        formatter = SandboxListFormatter()
        result_empty = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[])
        rendered = render_rich(formatter.to_rich(result_empty))
        assert "sbx_" not in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxListFormatter()
        result = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[])
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "sandboxes": [],
            "warnings": [],
            "errors": [],
            "fixes": [],
        }
