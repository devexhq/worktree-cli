"""Tests exercising the shared formatters."""

from worktree.common.formatters import format_warning_bullets


class FormatterTests:
    def test_format_warning_bullets(self):
        warnings = ["Warning 1", "Warning 2", "Split Line 1\nSplit Line 2"]
        formatted = format_warning_bullets(warnings)
        assert formatted == [
            "- Warning 1",
            "- Warning 2",
            "- Split Line 1",
            "  Split Line 2",
        ]
