"""Single-tier CLI integration tests for wt diff."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app

_PATCH_TEXT = (
    "diff --git a/file.txt b/file.txt\n"
    "index 111..222 100644\n"
    "--- a/file.txt\n"
    "+++ b/file.txt\n"
    "@@ -1 +1 @@\n"
    "-old line\n"
    "+new line\n"
)


def _write_session_diff(diff_workspace: Path, session_id: str) -> Path:
    """Write a real unified-diff patch file directly under .worktree/sessions/<id>/diff.patch."""
    session_dir = diff_workspace / ".worktree" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    patch_path = session_dir / "diff.patch"
    patch_path.write_text(_PATCH_TEXT, encoding="utf-8")
    return patch_path


class DiffCliIntegrationTests:
    """Typer runner integration tests for wt diff."""

    def test_diff_cli_known_session_renders_patch_exits_zero(self, cli_runner: CliRunner, diff_workspace: Path) -> None:
        """wt diff <session_id>: reads diff.patch off disk, exit 0, patch content in stdout."""
        _write_session_diff(diff_workspace, "sess-diff-1")

        result = cli_runner.invoke(app, ["-p", str(diff_workspace), "diff", "sess-diff-1"])

        assert result.exit_code == 0
        assert "diff --git a/file.txt b/file.txt" in result.stdout
        assert "-old line" in result.stdout
        assert "+new line" in result.stdout

    def test_diff_cli_unknown_session_exits_one(self, cli_runner: CliRunner, diff_workspace: Path) -> None:
        """wt diff <unknown-id>: exit 1, 'not found under .worktree/sessions' in stdout."""
        result = cli_runner.invoke(app, ["-p", str(diff_workspace), "diff", "unknown-session"])

        assert result.exit_code == 1
        assert "not found under .worktree/sessions" in result.stdout

    def test_diff_cli_json_emits_literal_wire_payload(self, cli_runner: CliRunner, diff_workspace: Path) -> None:
        """wt diff <session_id> --format json: stdout equals the literal DiffResultView envelope."""
        patch_path = _write_session_diff(diff_workspace, "sess-diff-1")

        result = cli_runner.invoke(app, ["-p", str(diff_workspace), "diff", "sess-diff-1", "--format", "json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "DiffResult",
            "payload": {
                "status": "ok",
                "session_id": "sess-diff-1",
                "artifact_path": str(patch_path),
                "relative_path": str(patch_path),
                "diff_text": _PATCH_TEXT,
                "raw": False,
                "full": False,
                "max_lines": 500,
                "total_lines": 7,
                "truncated": False,
                "truncated_lines": 0,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
