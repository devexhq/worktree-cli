"""Tests ensuring all fix strings are capitalized and properly rendered in formatters."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import FileSystem, render_rich
from worktree.cli.ui.formatters.config import (
    ConfigLoadFormatter,
    ConfigSetFormatter,
    ConfigValidateFormatter,
)
from worktree.cli.ui.formatters.diff import DiffResultFormatter
from worktree.cli.ui.formatters.history import HistoryListFormatter, HistoryShowFormatter
from worktree.cli.ui.formatters.init import WorkspaceInitFormatter
from worktree.cli.ui.formatters.sandbox import (
    SandboxApplyFormatter,
    SandboxCreateFormatter,
    SandboxDeleteFormatter,
    SandboxDiffFormatter,
    SandboxShowFormatter,
)
from worktree.core.bootstrap.models import WorkspaceInitResult
from worktree.core.bootstrap.services.bootstrap import BootstrapResult
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus, load_config
from worktree.core.config.mutate import ConfigSetResult, ConfigSetStatus, set_config_value_result
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
    validate_config_result,
)
from worktree.core.diff.models import DiffResult, DiffStatus
from worktree.core.history.models import HistoryListResult, HistoryShowResult, HistoryShowStatus
from worktree.core.patch.models import PatchApplyStatus
from worktree.core.patch.patch import validate_patch_text
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxDeleteResult,
    SandboxDeleteStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxShowResult,
    SandboxShowStatus,
)


def _assert_capitalized(fixes: list[str]) -> None:
    """Assert every fix string starts with an uppercase character."""
    assert len(fixes) > 0, "Expected at least one fix string"
    for fix in fixes:
        assert fix and (fix[0].isupper() or fix.startswith("`")), f"Fix string must start with uppercase: {fix!r}"


class TestFixesCapitalization:
    """Validate all core fix strings start with a capital letter."""

    def test_config_loader_fixes_capitalized(self, fs: FileSystem) -> None:
        # Not found
        res = load_config(path=fs.base_path / "nonexistent")
        assert not res.ok
        _assert_capitalized(res.fixes)

        # Directory
        dir_path = fs.base_path / ".worktree" / "config.json"
        dir_path.mkdir(parents=True)
        res_dir = load_config(path=fs.base_path)
        assert res_dir.status is ConfigLoadStatus.PATH_IS_DIRECTORY
        _assert_capitalized(res_dir.fixes)

    def test_config_validate_semantic_fixes_capitalized(self, fs: FileSystem) -> None:
        cfg = fs.base_path / ".worktree" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text('{"version": 1, "project": {"name": "test"}, "paths": {"db_path": "a\\nb"}}')
        res = validate_config_result(path=fs.base_path)
        assert not res.ok
        _assert_capitalized(res.fixes)

    def test_config_mutate_fixes_capitalized(self, fs: FileSystem) -> None:
        res = set_config_value_result("agent.model", "test", path=fs.base_path / "nonexistent")
        assert not res.ok
        _assert_capitalized(res.fixes)

    def test_patch_apply_fixes_capitalized(self, tmp_path: Path) -> None:
        res = validate_patch_text(
            "",
            max_files=10,
            max_patch_kb=100,
            reject_binary_changes=True,
            sandbox_path=tmp_path,
        )
        assert res.status is PatchApplyStatus.EMPTY_DIFF
        _assert_capitalized(res.fixes)

        res_large = validate_patch_text(
            "diff content",
            max_files=10,
            max_patch_kb=0,
            reject_binary_changes=True,
            sandbox_path=tmp_path,
        )
        assert res_large.status is PatchApplyStatus.TOO_LARGE
        _assert_capitalized(res_large.fixes)

        res_invalid = validate_patch_text(
            "not a valid diff",
            max_files=10,
            max_patch_kb=100,
            reject_binary_changes=True,
            sandbox_path=tmp_path,
        )
        assert res_invalid.status is PatchApplyStatus.INVALID_DIFF
        _assert_capitalized(res_invalid.fixes)


class TestFormattersRenderFixes:
    """Validate that CLI formatters render fixes under a Fix: header."""

    def test_config_load_formatter_renders_fixes(self) -> None:
        formatter = ConfigLoadFormatter()
        result = ConfigLoadResult(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=Path("/tmp/config.json"),
            errors=["Config file not found."],
            fixes=["Run `wt init` to create `.worktree/config.json`"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Fix:" in rendered
        assert "Run `wt init` to create `.worktree/config.json`" in rendered

    def test_config_validate_formatter_renders_fixes(self) -> None:
        formatter = ConfigValidateFormatter()
        result = ConfigValidationResult(
            status=ConfigValidationStatus.INVALID,
            config_path=Path("/tmp/config.json"),
            errors=["Invalid path"],
            fixes=["Use a plain relative path string without newlines or NUL bytes"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Fix:" in rendered
        assert "Use a plain relative path string without newlines or NUL bytes" in rendered

    def test_config_set_formatter_renders_fixes(self) -> None:
        formatter = ConfigSetFormatter()
        result = ConfigSetResult(
            status=ConfigSetStatus.SCHEMA_INVALID,
            config_path=Path("/tmp/config.json"),
            key="agent.invalid",
            errors=["Invalid key"],
            fixes=["Run `wt config validate` for details"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Fix:" in rendered
        assert "Run `wt config validate` for details" in rendered

    def test_diff_formatter_renders_fixes(self) -> None:
        formatter = DiffResultFormatter()
        result = DiffResult(
            status=DiffStatus.SESSION_NOT_FOUND,
            session_id="s123",
            errors=["Session not found"],
            fixes=["Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"],
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Fix:" in rendered
        assert "Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs" in rendered

    def test_history_formatters_render_fixes(self) -> None:
        show_formatter = HistoryShowFormatter()
        show_result = HistoryShowResult(
            status=HistoryShowStatus.NOT_FOUND,
            session_id="s456",
            errors=["Session 's456' not found."],
            fixes=["Run `wt history` to view past sessions"],
        )
        rendered_show = render_rich(show_formatter.to_rich(show_result))
        assert "Fix:" in rendered_show
        assert "Run `wt history` to view past sessions" in rendered_show

        list_formatter = HistoryListFormatter()
        list_result = HistoryListResult(
            errors=["Database locked"],
            fixes=["Wait for existing operation to complete"],
        )
        rendered_list = render_rich(list_formatter.to_rich(list_result))
        assert "Fix:" in rendered_list
        assert "Wait for existing operation to complete" in rendered_list

    def test_init_formatter_renders_fixes(self) -> None:
        formatter = WorkspaceInitFormatter()
        result = WorkspaceInitResult(
            bootstrap_result=BootstrapResult(
                root_path=Path("/tmp/repo/.worktree"),
                errors=["Directory conflict"],
                fixes=["Resolve the path conflict above, then rerun wt init."],
            )
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "Fix:" in rendered
        assert "Resolve the path conflict above, then rerun wt init." in rendered

    def test_sandbox_formatters_render_fixes(self) -> None:
        show_formatter = SandboxShowFormatter()
        show_res = SandboxShowResult(
            status=SandboxShowStatus.NOT_FOUND,
            errors=["Sandbox not found."],
            fixes=["Run `wt sandbox list` to see known sandboxes"],
        )
        rendered_show = render_rich(show_formatter.to_rich(show_res))
        assert "Fix:" in rendered_show
        assert "Run `wt sandbox list` to see known sandboxes" in rendered_show

        create_formatter = SandboxCreateFormatter()
        create_res = SandboxCreateResult(
            status=SandboxCreateStatus.CAPACITY_EXCEEDED,
            errors=["Max sandboxes reached"],
            fixes=["Run `wt prune` to remove stale sandboxes, or"],
        )
        rendered_create = render_rich(create_formatter.to_rich(create_res))
        assert "Fix:" in rendered_create
        assert "Run `wt prune` to remove stale sandboxes, or" in rendered_create

        apply_formatter = SandboxApplyFormatter()
        apply_res = SandboxApplyResult(
            status=SandboxApplyStatus.MAIN_REPO_DIRTY,
            sandbox_id="sbx-1",
            errors=["Main repo dirty"],
            fixes=["Commit or stash local changes in the main workspace, or"],
        )
        rendered_apply = render_rich(apply_formatter.to_rich(apply_res))
        assert "Fix:" in rendered_apply
        assert "Commit or stash local changes in the main workspace, or" in rendered_apply

        delete_formatter = SandboxDeleteFormatter()
        delete_res = SandboxDeleteResult(
            status=SandboxDeleteStatus.NOT_FOUND,
            sandbox_id="sbx-2",
            errors=["Sandbox 'sbx-2' not found."],
            fixes=["Run `wt sandbox list` to see known sandboxes"],
        )
        rendered_delete = render_rich(delete_formatter.to_rich(delete_res))
        assert "Fix:" in rendered_delete
        assert "Run `wt sandbox list` to see known sandboxes" in rendered_delete

        diff_formatter = SandboxDiffFormatter()
        diff_res = SandboxDiffResult(
            status=SandboxDiffStatus.GIT_FAILED,
            sandbox_id="sbx-3",
            errors=["Failed to diff"],
            fixes=["Inspect sandbox differences with `wt sandbox diff sbx-3`"],
        )
        rendered_diff = render_rich(diff_formatter.to_rich(diff_res))
        assert "Fix:" in rendered_diff
        assert "Inspect sandbox differences with `wt sandbox diff sbx-3`" in rendered_diff
