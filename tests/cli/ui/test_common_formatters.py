"""Unit tests for common UI formatters utilities."""

from __future__ import annotations

from rich.panel import Panel

from tests.helpers import render_rich
from worktree.cli.ui.formatters.common import (
    ERROR_PANEL_STYLE,
    build_error_panel,
    render_list_errors,
    render_list_fixes,
)


class TestRenderListErrors:
    """Tests for render_list_errors utility."""

    def test_render_list_errors_single(self) -> None:
        result = render_list_errors(["Something went wrong."])
        assert result == "Something went wrong."

    def test_render_list_errors_multiple(self) -> None:
        result = render_list_errors(["First error.", "Second error."])
        assert result == "First error.\n\nSecond error."

    def test_render_list_errors_empty_with_default(self) -> None:
        result = render_list_errors([], default="Fallback failure message.")
        assert result == "Fallback failure message."

    def test_render_list_errors_none_with_default(self) -> None:
        result = render_list_errors(None, default="Fallback failure message.")
        assert result == "Fallback failure message."

    def test_render_list_errors_empty_without_default(self) -> None:
        result = render_list_errors([])
        assert result == ""

    def test_render_list_errors_custom_separator(self) -> None:
        result = render_list_errors(["Line 1", "Line 2"], separator="\n")
        assert result == "Line 1\nLine 2"


class TestRenderListFixes:
    """Tests for render_list_fixes utility."""

    def test_render_list_fixes_single(self) -> None:
        result = render_list_fixes(["Run `wt init` to set up workspace."])
        assert result == "Fix:\n- Run `wt init` to set up workspace."

    def test_render_list_fixes_multiple(self) -> None:
        result = render_list_fixes(["Check permissions.", "Rerun command."])
        assert result == "Fix:\n- Check permissions.\n- Rerun command."

    def test_render_list_fixes_empty(self) -> None:
        assert render_list_fixes([]) == ""

    def test_render_list_fixes_none(self) -> None:
        assert render_list_fixes(None) == ""

    def test_render_list_fixes_custom_header_and_bullet(self) -> None:
        result = render_list_fixes(["Action A", "Action B"], header="Remediation:", bullet="* ")
        assert result == "Remediation:\n* Action A\n* Action B"


class TestBuildErrorPanel:
    """Tests for build_error_panel utility."""

    def test_build_error_panel_with_errors_and_fixes(self) -> None:
        panel = build_error_panel(
            "Test Error",
            errors=["Operation failed.", "Details missing."],
            fixes=["Try again with --force."],
        )
        assert isinstance(panel, Panel)
        assert panel.title == "Test Error"
        assert panel.border_style == ERROR_PANEL_STYLE

        rendered = render_rich(panel)
        assert "Operation failed." in rendered
        assert "Details missing." in rendered
        assert "Fix:" in rendered
        assert "- Try again with --force." in rendered

    def test_build_error_panel_fallback_default(self) -> None:
        panel = build_error_panel(
            "Fallback Title",
            errors=[],
            default="Default error message.",
            fixes=["Rerun command."],
        )
        rendered = render_rich(panel)
        assert "Default error message." in rendered
        assert "Fix:" in rendered
        assert "- Rerun command." in rendered

    def test_build_error_panel_no_fixes(self) -> None:
        panel = build_error_panel(
            "No Fixes",
            errors=["Only error occurred."],
        )
        rendered = render_rich(panel)
        assert "Only error occurred." in rendered
        assert "Fix:" not in rendered

    def test_build_error_panel_fit_and_custom_style(self) -> None:
        panel = build_error_panel(
            "Fit Title",
            errors=["Error line."],
            border_style="magenta",
            fit=True,
        )
        assert panel.border_style == "magenta"
        rendered = render_rich(panel)
        assert "Error line." in rendered
