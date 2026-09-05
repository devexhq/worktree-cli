"""Tier 2 presentation contract tests for SandboxPruneFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_prune import SandboxPruneFormatter
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxPruneResult,
    StaleSandboxCategory,
)


class SandboxPruneFormatterTests:
    """Presentation contract tests for SandboxPruneFormatter."""

    def test_to_rich_when_empty_omits_items(self) -> None:
        formatter = SandboxPruneFormatter()
        result = SandboxPruneResult()
        rendered = render_rich(formatter.to_rich(result))
        assert "feature/" not in rendered

    def test_to_rich_with_items_contains_item_info(self) -> None:
        formatter = SandboxPruneFormatter()
        item = PrunedItem(
            category=StaleSandboxCategory.STALE_BRANCH,
            identifier="feature/stale",
            action=PruneAction.PRUNED,
            reason="Cleaned up branch",
        )
        result = SandboxPruneResult(items=[item])
        rendered = render_rich(formatter.to_rich(result))
        assert "feature/stale" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = SandboxPruneFormatter()
        result = SandboxPruneResult()
        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "dry_run": False,
            "force": False,
            "items": [],
            "warnings": [],
            "errors": [],
            "fixes": [],
        }
