"""Tier 2 presentation contract tests for PrunedItemFormatter."""

from __future__ import annotations

import pytest

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.pruned_item import PrunedItemFormatter
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    StaleSandboxCategory,
)


class PrunedItemFormatterTests:
    """Presentation contract tests for PrunedItemFormatter."""

    @pytest.mark.parametrize(
        ("item", "expected_substrings"),
        [
            pytest.param(
                PrunedItem(
                    category=StaleSandboxCategory.STALE_BRANCH,
                    identifier="feature/1",
                    action=PruneAction.PRUNED,
                    reason="Would prune stale branch",
                ),
                ["feature/1"],
                id="dry_run_stale_branch",
            ),
            pytest.param(
                PrunedItem(
                    category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                    identifier="sbx_12345678",
                    action=PruneAction.PRUNED,
                    reason="Cleaned up orphaned directory",
                ),
                ["sbx_12345678"],
                id="pruned_orphaned_directory",
            ),
            pytest.param(
                PrunedItem(
                    category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                    identifier="sbx_dirty",
                    action=PruneAction.SKIPPED,
                    reason="Contains uncommitted changes",
                ),
                ["sbx_dirty"],
                id="skipped_dirty_directory",
            ),
            pytest.param(
                PrunedItem(
                    category=StaleSandboxCategory.STALE_WORKTREE_REF,
                    identifier="/tmp/sbx",
                    action=PruneAction.FAILED,
                    error="Permission denied",
                ),
                ["/tmp/sbx", "Permission denied"],
                id="failed_stale_worktree_ref",
            ),
        ],
    )
    def test_to_rich_renders_action_and_identifier(
        self,
        item: PrunedItem,
        expected_substrings: list[str],
    ) -> None:
        formatter = PrunedItemFormatter()
        rendered = render_rich(formatter.to_rich(item))
        for expected in expected_substrings:
            assert expected in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = PrunedItemFormatter()
        item = PrunedItem(
            category=StaleSandboxCategory.STALE_BRANCH,
            identifier="feature/1",
            action=PruneAction.PRUNED,
            reason="Would prune",
        )
        dumped = formatter.to_json_serializable(item)
        assert dumped == {
            "category": "stale_branch",
            "identifier": "feature/1",
            "action": "pruned",
            "path": None,
            "branch_name": None,
            "session_id": None,
            "reason": "Would prune",
            "error": None,
        }
