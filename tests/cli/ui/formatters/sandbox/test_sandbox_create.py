"""Tier 2 presentation contract tests for SandboxCreateFormatter."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_create import SandboxCreateFormatter
from worktree.core.sandbox.models import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)


class SandboxCreateFormatterTests:
    """Presentation contract tests for SandboxCreateFormatter."""

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxCreateFormatter()
        session = SandboxSession(
            session_id="sbx_create123",
            target_branch="worktree/sandbox-create123",
            sandbox_path=Path("/tmp/sbx_create123"),
            base_commit="def5678",
            created_at="2026-08-31T20:00:00Z",
        )
        result = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
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
        }

    def test_to_rich_when_created_contains_session_id(self) -> None:
        formatter = SandboxCreateFormatter()
        session = SandboxSession(
            session_id="sbx_create123",
            target_branch="worktree/sandbox-create123",
            sandbox_path=Path("/tmp/sbx_create123"),
            base_commit="def5678",
            created_at="2026-08-31T20:00:00Z",
        )
        result_ok = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)
        rich_ok = formatter.to_rich(result_ok)
        assert rich_ok is not None
        rendered_ok = render_rich(rich_ok)
        assert "sbx_create123" in rendered_ok

    def test_to_rich_failure_contains_errors(self) -> None:
        formatter = SandboxCreateFormatter()
        result_fail = SandboxCreateResult(
            status=SandboxCreateStatus.GIT_FAILED,
            errors=["Git checkout failed."],
        )
        rich_fail = formatter.to_rich(result_fail)
        assert rich_fail is not None
        rendered_fail = render_rich(rich_fail)
        assert "Git checkout failed." in rendered_fail
