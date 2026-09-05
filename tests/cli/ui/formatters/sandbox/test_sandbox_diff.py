"""Tier 2 presentation contract tests for SandboxDiffFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_diff import SandboxDiffFormatter
from worktree.core.sandbox.models import (
    SandboxDiffResult,
    SandboxDiffStatus,
)


class SandboxDiffFormatterTests:
    """Presentation contract tests for SandboxDiffFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxDiffFormatter()
        result = SandboxDiffResult(
            status=SandboxDiffStatus.OK,
            sandbox_id="sbx_diff",
            diff_text="diff --git ...",
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "sandbox_id": "sbx_diff",
            "diff_text": "diff --git ...",
            "stat_text": "",
            "files_changed": [],
            "warnings": [],
            "errors": [],
            "fixes": [],
        }

    def test_to_rich_diff_contains_diff_content(self) -> None:
        formatter = SandboxDiffFormatter()
        result = SandboxDiffResult(
            status=SandboxDiffStatus.OK,
            sandbox_id="sbx_diff",
            diff_text="+new_line",
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "+new_line" in rendered

    def test_to_rich_empty_diff_contains_sandbox_id(self) -> None:
        formatter = SandboxDiffFormatter()
        result = SandboxDiffResult(
            status=SandboxDiffStatus.EMPTY_DIFF,
            sandbox_id="sbx_empty",
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_empty" in rendered
