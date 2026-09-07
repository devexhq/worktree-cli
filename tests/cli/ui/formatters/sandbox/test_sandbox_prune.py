"""Tier 2 presentation contract tests for SandboxPruneFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.sandbox.sandbox_prune import SandboxPruneFormatter
from worktree.cli.ui.formatters.sandbox.sandbox_views import (
    PrunedItemView,
    SandboxPruneView,
)
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxPruneResult,
    SandboxPruneStatus,
    StaleSandboxCategory,
)

EMPTY_PRUNE = FormatterCase(
    data=SandboxPruneResult(
        status=SandboxPruneStatus.OK,
        dry_run=False,
        force=False,
        items=[],
    ),
    view=SandboxPruneView(
        status=SandboxPruneStatus.OK,
        dry_run=False,
        force=False,
        items=[],
        pruned_count=0,
        skipped_count=0,
        failed_count=0,
        errors=[],
        warnings=[],
        fixes=[],
    ),
    render_expectations=["No stale sandboxes found."],
)

PRUNED_MULTIPLE_ITEMS = FormatterCase(
    data=SandboxPruneResult(
        status=SandboxPruneStatus.PARTIAL_SUCCESS,
        dry_run=False,
        force=True,
        items=[
            PrunedItem(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier="feature/stale",
                action=PruneAction.PRUNED,
                reason="Cleaned up branch",
            ),
            PrunedItem(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                identifier="sbx_dirty",
                action=PruneAction.SKIPPED,
                reason="Contains uncommitted changes",
            ),
            PrunedItem(
                category=StaleSandboxCategory.STALE_WORKTREE_REF,
                identifier="/tmp/sbx_ref",
                action=PruneAction.FAILED,
                error="Ref locked",
            ),
        ],
        errors=["Ref lock failure"],
    ),
    view=SandboxPruneView(
        status=SandboxPruneStatus.PARTIAL_SUCCESS,
        dry_run=False,
        force=True,
        items=[
            PrunedItemView(
                category=StaleSandboxCategory.STALE_BRANCH,
                category_label="stale branch",
                identifier="feature/stale",
                action=PruneAction.PRUNED,
                is_dry_run=False,
                reason="Cleaned up branch",
            ),
            PrunedItemView(
                category=StaleSandboxCategory.ORPHANED_DIRECTORY,
                category_label="orphaned directory",
                identifier="sbx_dirty",
                action=PruneAction.SKIPPED,
                is_dry_run=False,
                reason="Contains uncommitted changes",
            ),
            PrunedItemView(
                category=StaleSandboxCategory.STALE_WORKTREE_REF,
                category_label="stale worktree ref",
                identifier="/tmp/sbx_ref",
                action=PruneAction.FAILED,
                is_dry_run=False,
                error="Ref locked",
            ),
        ],
        pruned_count=1,
        skipped_count=1,
        failed_count=1,
        errors=["Ref lock failure"],
        warnings=[],
        fixes=[],
    ),
    render_expectations=["feature/stale", "sbx_dirty", "/tmp/sbx_ref"],
)

DRY_RUN_PRUNE = FormatterCase(
    data=SandboxPruneResult(
        status=SandboxPruneStatus.OK,
        dry_run=True,
        force=False,
        items=[
            PrunedItem(
                category=StaleSandboxCategory.STALE_BRANCH,
                identifier="feature/dry",
                action=PruneAction.PRUNED,
                reason="Stale branch",
            ),
        ],
    ),
    view=SandboxPruneView(
        status=SandboxPruneStatus.OK,
        dry_run=True,
        force=False,
        items=[
            PrunedItemView(
                category=StaleSandboxCategory.STALE_BRANCH,
                category_label="stale branch",
                identifier="feature/dry",
                action=PruneAction.PRUNED,
                is_dry_run=True,
                reason="Stale branch",
            ),
        ],
        pruned_count=1,
        skipped_count=0,
        failed_count=0,
        errors=[],
        warnings=[],
        fixes=[],
    ),
    render_expectations=["feature/dry"],
)

WITH_WARNINGS_AND_FIXES = FormatterCase(
    data=SandboxPruneResult(
        status=SandboxPruneStatus.OK,
        dry_run=False,
        force=False,
        warnings=["Warning message"],
        fixes=["Fix suggestion"],
    ),
    view=SandboxPruneView(
        status=SandboxPruneStatus.OK,
        dry_run=False,
        force=False,
        items=[],
        pruned_count=0,
        skipped_count=0,
        failed_count=0,
        errors=[],
        warnings=["Warning message"],
        fixes=["Fix suggestion"],
    ),
    render_expectations=["No stale sandboxes found."],
)

PRUNE_CASES = [
    pytest.param(EMPTY_PRUNE, id="empty_prune"),
    pytest.param(PRUNED_MULTIPLE_ITEMS, id="pruned_multiple_items"),
    pytest.param(DRY_RUN_PRUNE, id="dry_run_prune"),
    pytest.param(WITH_WARNINGS_AND_FIXES, id="with_warnings_and_fixes"),
]

PRUNE_PAYLOAD_CASES = [
    pytest.param(
        EMPTY_PRUNE,
        {
            "status": "ok",
            "dry_run": False,
            "force": False,
            "items": [],
            "pruned_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="empty_prune",
    ),
    pytest.param(
        PRUNED_MULTIPLE_ITEMS,
        {
            "status": "partial_success",
            "dry_run": False,
            "force": True,
            "items": [
                {
                    "category": "stale_branch",
                    "category_label": "stale branch",
                    "identifier": "feature/stale",
                    "action": "pruned",
                    "is_dry_run": False,
                    "path": None,
                    "branch_name": None,
                    "session_id": None,
                    "reason": "Cleaned up branch",
                    "error": None,
                },
                {
                    "category": "orphaned_directory",
                    "category_label": "orphaned directory",
                    "identifier": "sbx_dirty",
                    "action": "skipped",
                    "is_dry_run": False,
                    "path": None,
                    "branch_name": None,
                    "session_id": None,
                    "reason": "Contains uncommitted changes",
                    "error": None,
                },
                {
                    "category": "stale_worktree_ref",
                    "category_label": "stale worktree ref",
                    "identifier": "/tmp/sbx_ref",
                    "action": "failed",
                    "is_dry_run": False,
                    "path": None,
                    "branch_name": None,
                    "session_id": None,
                    "reason": "",
                    "error": "Ref locked",
                },
            ],
            "pruned_count": 1,
            "skipped_count": 1,
            "failed_count": 1,
            "errors": ["Ref lock failure"],
            "warnings": [],
            "fixes": [],
        },
        id="pruned_multiple_items",
    ),
]


class SandboxPruneFormatterTests:
    """Presentation contract tests for SandboxPruneFormatter."""

    @pytest.mark.parametrize("case", PRUNE_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[SandboxPruneResult, SandboxPruneView]) -> None:
        """Verify transform derives the exact SandboxPruneView model representation."""
        assert SandboxPruneFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), PRUNE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[SandboxPruneResult, SandboxPruneView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert SandboxPruneFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", PRUNE_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[SandboxPruneResult, SandboxPruneView]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(SandboxPruneFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered
        for error in view.errors:
            assert error in rendered
