"""Tier 2 presentation contract tests for SandboxDeleteFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_delete import SandboxDeleteFormatter
from worktree.core.sandbox.models import (
    SandboxDeleteResult,
    SandboxDeleteStatus,
)


class SandboxDeleteFormatterTests:
    """Presentation contract tests for SandboxDeleteFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxDeleteFormatter()
        result = SandboxDeleteResult(
            status=SandboxDeleteStatus.DELETED,
            sandbox_id="sbx_del",
            deleted=True,
        )
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "deleted",
            "sandbox_id": "sbx_del",
            "sandbox": None,
            "deleted": True,
            "warnings": [],
            "errors": [],
            "fixes": [],
        }

    def test_to_rich_when_deleted_renders_sandbox_id(self) -> None:
        formatter = SandboxDeleteFormatter()
        result = SandboxDeleteResult(
            status=SandboxDeleteStatus.DELETED,
            sandbox_id="sbx_del",
            deleted=True,
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_del" in rendered

    def test_to_rich_when_not_found_renders_error_and_sandbox_id(self) -> None:
        formatter = SandboxDeleteFormatter()
        result = SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_FOUND,
            sandbox_id="sbx_missing",
            errors=["Sandbox 'sbx_missing' not found."],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "sbx_missing" in rendered
        assert "Sandbox 'sbx_missing' not found." in rendered
