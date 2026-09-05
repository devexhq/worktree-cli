"""Tier 2 presentation contract tests for SandboxApplyFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_apply import SandboxApplyFormatter
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
)


class SandboxApplyFormatterTests:
    """Presentation contract tests for SandboxApplyFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxApplyFormatter()
        result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_1",
            strategy=SandboxApplyStrategy.SQUASH,
            commit_sha="abc",
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "sandbox_id": "sbx_1",
            "strategy": "squash",
            "touched_files": [],
            "conflicting_files": [],
            "cleaned_up": False,
            "commit_sha": "abc",
            "warnings": [],
            "errors": [],
            "fixes": [],
        }

    def test_to_rich_when_applied_contains_commit_sha(self) -> None:
        formatter = SandboxApplyFormatter()
        result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_1",
            strategy=SandboxApplyStrategy.SQUASH,
            commit_sha="abc1234",
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_1" in rendered
        assert "squash" in rendered
        assert "abc1234" in rendered

    def test_to_rich_failure_contains_errors_and_fixes(self) -> None:
        formatter = SandboxApplyFormatter()
        result = SandboxApplyResult(
            status=SandboxApplyStatus.GIT_FAILED,
            sandbox_id="sbx_1",
            errors=["Merge conflict"],
            fixes=["Resolve manually"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Merge conflict" in rendered
        assert "Resolve manually" in rendered
