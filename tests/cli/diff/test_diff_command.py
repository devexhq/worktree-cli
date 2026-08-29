"""Comprehensive unit and CLI integration tests for ``wt diff``."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, make_cli_context
from worktree.cli import app
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


class DiffCommandDirectTests:
    """Direct unit tests for diff_command pure function."""

    def test_diff_command_direct_success(self, fs: FileSystem) -> None:
        """Verify diff_command returns OK DiffResult when diff.patch exists."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_cmd_1" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        context = make_cli_context(cwd=fs.base_path)
        result = diff_command(context, "sbx_cmd_1")
        assert result.ok
        assert result.status == DiffStatus.OK
        assert result.session_id == "sbx_cmd_1"
        assert result.diff_text == _SAMPLE_DIFF

    def test_diff_command_direct_raw(self, fs: FileSystem) -> None:
        """Verify diff_command with raw=True executes cleanly."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_raw_1" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        context = make_cli_context(cwd=fs.base_path)
        result = diff_command(context, "sbx_raw_1", raw=True)
        assert result.ok
        assert result.status == DiffStatus.OK

    def test_diff_command_direct_empty(self, fs: FileSystem) -> None:
        """Verify diff_command with empty diff returns EMPTY_DIFF status."""
        fs.create_config_file()
        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_empty_1" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text("", encoding="utf-8")

        context = make_cli_context(cwd=fs.base_path)
        result = diff_command(context, "sbx_empty_1")
        assert result.ok
        assert result.status == DiffStatus.EMPTY_DIFF


class DiffCliIntegrationTests:
    """CLI integration tests for ``wt diff`` command."""

    def test_cli_diff_explicit_session_formatted(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff <session_id>' renders session header and syntax diff."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_a1b2c3d4" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        result = runner.invoke(app, ["diff", "sbx_a1b2c3d4"])
        assert result.exit_code == 0
        assert "Session: sbx_a1b2c3d4" in result.output
        assert ".worktree/sessions/sbx_a1b2c3d4/diff.patch" in result.output
        assert "def old(): pass" in result.output
        assert "def new(): pass" in result.output

    def test_cli_diff_raw_flag(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff <session_id> --raw' outputs plain text diff without header."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_raw" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(_SAMPLE_DIFF, encoding="utf-8")

        result = runner.invoke(app, ["diff", "sbx_raw", "--raw"])
        assert result.exit_code == 0
        assert "Session: sbx_raw" not in result.output
        assert _SAMPLE_DIFF.strip() in result.output

    def test_cli_diff_auto_picks_latest_session(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff' with no args selects the latest session directory."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        sessions_dir = fs.base_path / ".worktree" / "sessions"

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

    def test_cli_diff_empty_patch_exits_0(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff' on empty patch prints clean message and exits 0."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        patch_file = fs.base_path / ".worktree" / "sessions" / "sbx_empty" / "diff.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text("   \n", encoding="utf-8")

        result = runner.invoke(app, ["diff", "sbx_empty"])
        assert result.exit_code == 0
        assert "No changes recorded for session sbx_empty." in result.output

    def test_cli_diff_missing_explicit_session_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff <missing_session>' renders Session Not Found panel and exits 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        result = runner.invoke(app, ["diff", "sbx_99999999"])
        assert result.exit_code == 1
        assert "Session Not Found" in result.output
        assert "Session 'sbx_99999999' not found under .worktree/sessions/." in result.output

    def test_cli_diff_no_sessions_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff' with no sessions renders Session Not Found panel and exits 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 1
        assert "Session Not Found" in result.output
        assert "No loop run sessions found." in result.output

    def test_cli_diff_missing_patch_artifact_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff <session>' without diff.patch renders Diff Not Found panel and exits 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)

        session_dir = fs.base_path / ".worktree" / "sessions" / "sbx_no_patch"
        session_dir.mkdir(parents=True, exist_ok=True)

        result = runner.invoke(app, ["diff", "sbx_no_patch"])
        assert result.exit_code == 1
        assert "Diff Not Found" in result.output
        assert "Session 'sbx_no_patch' has no diff artifact." in result.output

    def test_cli_diff_uninitialized_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 'wt diff' in uninitialized directory renders error and exits 1."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 1
        assert "Not initialized or invalid config" in result.output or "Worktree Not Initialized" in result.output
