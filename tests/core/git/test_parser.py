"""Unit tests for porcelain git worktree list parsing."""

from __future__ import annotations

from pathlib import Path

from tests.harness.matchers import assert_model_equal
from worktree.core.git.models import GitWorktreeEntry
from worktree.core.git.runner import parse_worktree_porcelain


class GitWorktreeOutputParserTests:
    """Unit tests for porcelain git worktree list parsing."""

    def test_parse_worktree_machine_output_parses_detached_and_locked_states(self) -> None:
        """Parse multi-stanza porcelain output containing detached and locked states."""
        raw = (
            "worktree /path/to/wt\n"
            "HEAD 1234abc\n"
            "branch refs/heads/feature\n"
            "\n"
            "worktree /path/2\n"
            "detached\n"
            "locked manual\n"
            "\n"
        )

        entries = parse_worktree_porcelain(raw)

        assert len(entries) == 2
        assert_model_equal(
            entries[0],
            GitWorktreeEntry(
                path=Path("/path/to/wt"),
                head_sha="1234abc",
                branch="feature",
                is_bare=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
                prunable_reason=None,
            ),
        )
        assert_model_equal(
            entries[1],
            GitWorktreeEntry(
                path=Path("/path/2"),
                head_sha="",
                branch=None,
                is_bare=False,
                is_detached=True,
                is_locked=True,
                is_prunable=False,
                prunable_reason=None,
            ),
        )

    def test_parse_worktree_machine_output_parses_bare_and_prunable_states(self) -> None:
        """Parse multi-stanza porcelain output containing bare and prunable states."""
        raw = (
            "worktree /repo/bare\n"
            "bare\n"
            "\n"
            "worktree /repo/prunable1\n"
            "HEAD 5678def\n"
            "prunable gitdir file points to non-existent location\n"
            "\n"
            "worktree /repo/prunable2\n"
            "prunable\n"
            "\n"
        )

        entries = parse_worktree_porcelain(raw)

        assert len(entries) == 3
        assert_model_equal(
            entries[0],
            GitWorktreeEntry(
                path=Path("/repo/bare"),
                head_sha="",
                branch=None,
                is_bare=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
                prunable_reason=None,
            ),
        )
        assert_model_equal(
            entries[1],
            GitWorktreeEntry(
                path=Path("/repo/prunable1"),
                head_sha="5678def",
                branch=None,
                is_bare=False,
                is_detached=False,
                is_locked=False,
                is_prunable=True,
                prunable_reason="gitdir file points to non-existent location",
            ),
        )
        assert_model_equal(
            entries[2],
            GitWorktreeEntry(
                path=Path("/repo/prunable2"),
                head_sha="",
                branch=None,
                is_bare=False,
                is_detached=False,
                is_locked=False,
                is_prunable=True,
                prunable_reason=None,
            ),
        )

    def test_parse_worktree_machine_output_returns_empty_list_for_empty_input(self) -> None:
        """Parse empty or blank string returning empty list."""
        entries = parse_worktree_porcelain("")

        assert entries == []
