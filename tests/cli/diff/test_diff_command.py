"""Comprehensive unit and CLI integration tests for ``wt diff``."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from tests.helpers import FileSystem, make_cli_context
from worktree.cli import app
from worktree.cli.context import CliContext
from worktree.cli.diff.commands.root import diff_command
from worktree.core.diff import DiffStatus

runner = CliRunner()

_SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass
"""


@pytest.fixture
def configured_project(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Establish an initialized project with config.json and set cwd."""
    fs.create_config_file()
    monkeypatch.chdir(fs.base_path)
    return fs.base_path


@pytest.fixture
def sample_diff(configured_project: Path) -> Iterator[tuple[Path, CliContext]]:
    """Establish baseline sample session diff artifact and CliContext."""
    patch_file = configured_project / ".worktree" / "sessions" / "sbx_diff_cmd_1" / "diff.patch"
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")
    context = make_cli_context(cwd=configured_project)

    yield patch_file, context


class DiffCommandRootTests:
    """Direct unit tests for diff_command pure function."""

    def test_diff_command_direct_success(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify diff_command returns OK result when diff.patch exists."""
        _, context = sample_diff
        result = diff_command(context, "sbx_diff_cmd_1", full=True)
        assert result.ok
        assert result.status == DiffStatus.OK

    def test_diff_command_direct_raw(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify diff_command with raw=True executes cleanly."""
        _, context = sample_diff
        result = diff_command(context, "sbx_diff_cmd_1", raw=True)
        assert result.ok
        assert result.status == DiffStatus.OK

    def test_diff_command_direct_full(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify diff_command with full=True executes cleanly."""
        _, context = sample_diff
        result = diff_command(context, "sbx_diff_cmd_1", full=True)
        assert result.ok
        assert result.status == DiffStatus.OK

    def test_diff_command_direct_empty(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify diff_command with empty diff returns EMPTY_DIFF status."""
        patch_file, context = sample_diff
        patch_file.write_text("")
        result = diff_command(context, "sbx_diff_cmd_1", full=True)
        assert result.ok
        assert result.status == DiffStatus.EMPTY_DIFF


class DiffCliIntegrationTests:
    """CLI integration tests for ``wt diff`` command."""

    def test_cli_diff_explicit_session_formatted(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <session_id>' renders session header and syntax diff."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        result = runner.invoke(app, ["diff", session_id])
        assert result.exit_code == 0
        assert f"Session: {session_id}" in result.output
        assert f".worktree/sessions/{session_id}/diff.patch" in result.output
        assert "def old(): pass" in result.output
        assert "def new(): pass" in result.output

    def test_cli_diff_raw_flag(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <session_id> --raw' outputs plain text diff without header."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        result = runner.invoke(app, ["diff", session_id, "--raw"])
        assert result.exit_code == 0
        assert f"Session: {session_id}" not in result.output
        assert _SAMPLE_DIFF.strip() in result.output

    def test_cli_diff_full_flag(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <session_id> --full' renders formatted output with session header."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        result = runner.invoke(app, ["diff", session_id, "--full"])
        assert result.exit_code == 0
        assert f"Session: {session_id}" in result.output
        assert "def old(): pass" in result.output
        assert "def new(): pass" in result.output

    def test_cli_diff_raw_precedence_over_full(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify passing both --raw and --full cleanly outputs raw text."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        result = runner.invoke(app, ["diff", session_id, "--raw", "--full"])
        assert result.exit_code == 0
        assert f"Session: {session_id}" not in result.output
        assert _SAMPLE_DIFF.strip() in result.output

    def test_cli_diff_large_patch_tty_truncation(
        self, sample_diff: tuple[Path, CliContext], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify 'wt diff <session_id>' truncates when running in simulated TTY."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name
        monkeypatch.setattr(Console, "is_terminal", property(lambda self: True))

        large_diff = "\n".join([f"+line {i}" for i in range(1, 550)])
        patch_file.write_text(large_diff, encoding="utf-8")

        result = runner.invoke(app, ["diff", session_id])
        assert result.exit_code == 0
        assert f"Session: {session_id}" in result.output
        assert "+line 500" in result.output
        assert "+line 501" not in result.output
        assert "... [diff truncated: showing 500 of 549 lines]" in result.output
        assert f"run `wt diff {session_id} --full` to view complete formatted output" in result.output
        assert f"run `wt diff {session_id} --full | less -R` to page through formatted diff" in result.output

    def test_cli_diff_large_patch_non_tty_full(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <session_id>' in non-TTY (default runner) outputs entire diff without truncation."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        large_diff = "\n".join([f"+line {i}" for i in range(1, 550)])
        patch_file.write_text(large_diff, encoding="utf-8")

        result = runner.invoke(app, ["diff", session_id])
        assert result.exit_code == 0
        assert f"Session: {session_id}" in result.output
        assert "+line 549" in result.output
        assert "diff truncated" not in result.output

    def test_cli_diff_auto_picks_latest_session(self, configured_project: Path) -> None:
        """Verify 'wt diff' with no args selects the latest session directory."""
        sessions_dir = configured_project / ".worktree" / "sessions"

        older_sess = sessions_dir / "sbx_old"
        older_sess.mkdir(parents=True, exist_ok=True)
        (older_sess / "diff.patch").write_text("old diff\n", encoding="utf-8")
        os.utime(older_sess, (time.time() - 200, time.time() - 200))

        newer_sess = sessions_dir / "sbx_new"
        newer_sess.mkdir(parents=True, exist_ok=True)
        (newer_sess / "diff.patch").write_text(_SAMPLE_DIFF, encoding="utf-8")
        os.utime(newer_sess, (time.time(), time.time()))

        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 0
        assert "Session: sbx_new" in result.output
        assert "def new(): pass" in result.output

    def test_cli_diff_empty_patch_exits_0(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff' on empty patch prints clean message and exits 0."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name
        patch_file.write_text("   \n", encoding="utf-8")

        result = runner.invoke(app, ["diff", session_id])
        assert result.exit_code == 0
        assert f"No changes recorded for session {session_id}." in result.output

    def test_cli_diff_missing_explicit_session_exits_1(self, configured_project: Path) -> None:
        """Verify 'wt diff <missing_session>' renders Session Not Found panel and exits 1."""
        result = runner.invoke(app, ["diff", "sbx_99999999"])
        assert result.exit_code == 1
        assert "Session Not Found" in result.output
        assert "Session 'sbx_99999999' not found under .worktree/sessions/." in result.output

    def test_cli_diff_no_sessions_exits_1(self, configured_project: Path) -> None:
        """Verify 'wt diff' with no sessions renders Session Not Found panel and exits 1."""
        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 1
        assert "Session Not Found" in result.output
        assert "No loop run sessions found." in result.output

    def test_cli_diff_missing_patch_artifact_exits_1(self, configured_project: Path) -> None:
        """Verify 'wt diff <session>' without diff.patch renders Diff Not Found panel and exits 1."""
        session_dir = configured_project / ".worktree" / "sessions" / "sbx_no_patch"
        session_dir.mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["diff", "sbx_no_patch"])
        assert result.exit_code == 1
        assert "Diff Not Found" in result.output
        assert "Session 'sbx_no_patch' has no diff artifact." in result.output

    def test_cli_diff_format_json_success(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <session_id> --format json' outputs NDJSON envelope."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name

        result = runner.invoke(app, ["diff", session_id, "--format", "json"])
        assert result.exit_code == 0

        lines = [line for line in result.output.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "DiffResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["session_id"] == session_id
        assert payload["payload"]["diff_text"] == _SAMPLE_DIFF

    def test_cli_diff_format_json_missing_session(self, configured_project: Path) -> None:
        """Verify 'wt diff <missing> --format json' outputs NDJSON envelope and exits 1."""
        result = runner.invoke(app, ["diff", "sbx_nonexistent", "--format", "json"])
        assert result.exit_code == 1

        lines = [line for line in result.output.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "DiffResult"
        assert payload["payload"]["status"] == "session_not_found"
        assert payload["payload"]["session_id"] == "sbx_nonexistent"
        assert len(payload["payload"]["errors"]) > 0

    def test_cli_diff_format_json_empty_diff(self, sample_diff: tuple[Path, CliContext]) -> None:
        """Verify 'wt diff <empty> --format json' outputs NDJSON envelope for empty diff and exits 0."""
        patch_file, _ = sample_diff
        session_id = patch_file.parent.name
        patch_file.write_text("")

        result = runner.invoke(app, ["diff", session_id, "--format", "json"])
        assert result.exit_code == 0

        lines = [line for line in result.output.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "DiffResult"
        assert payload["payload"]["status"] == "empty_diff"
        assert payload["payload"]["diff_text"] == ""

    def test_cli_diff_uninitialized_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff' in uninitialized directory renders error and exits 1 via CliContext."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 1
        assert "Config Error" in result.output
        assert "CONFIG_NOT_FOUND" in result.output
