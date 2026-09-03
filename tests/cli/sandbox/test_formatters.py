"""Unit tests for sandbox ComponentFormatters and UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.text import Text

from tests.helpers import render_rich
from worktree.cli.sandbox.formatters import (
    PrunedItemFormatter,
    SandboxCreateFormatter,
    SandboxListFormatter,
    SandboxShowFormatter,
)
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxListResult,
    SandboxListStatus,
    SandboxSession,
    SandboxShowResult,
    SandboxShowStatus,
    StaleSandboxCategory,
)


def test_pruned_item_formatter_to_rich() -> None:
    formatter = PrunedItemFormatter()

    # Dry run item
    dry_item = PrunedItem(
        category=StaleSandboxCategory.STALE_BRANCH,
        identifier="feature/1",
        action=PruneAction.PRUNED,
        reason="Would prune stale branch",
    )
    rich_dry = formatter.to_rich(dry_item)
    assert isinstance(rich_dry, Text)
    assert "• Would prune stale branch: feature/1" in rich_dry.plain

    # Real pruned item
    pruned_item = PrunedItem(
        category=StaleSandboxCategory.ORPHANED_DIRECTORY,
        identifier="sbx_12345678",
        action=PruneAction.PRUNED,
        reason="Cleaned up orphaned directory",
    )
    rich_pruned = formatter.to_rich(pruned_item)
    assert "• Pruned orphaned directory: sbx_12345678" in rich_pruned.plain

    # Skipped item
    skipped_item = PrunedItem(
        category=StaleSandboxCategory.ORPHANED_DIRECTORY,
        identifier="sbx_dirty",
        action=PruneAction.SKIPPED,
        reason="Contains uncommitted changes",
    )
    rich_skipped = formatter.to_rich(skipped_item)
    assert "• Skipped orphaned directory: sbx_dirty" in rich_skipped.plain

    # Failed item
    failed_item = PrunedItem(
        category=StaleSandboxCategory.STALE_WORKTREE_REF,
        identifier="/tmp/sbx",
        action=PruneAction.FAILED,
        error="Permission denied",
    )
    rich_failed = formatter.to_rich(failed_item)
    assert "• Failed to prune stale worktree ref: /tmp/sbx (Permission denied)" in rich_failed.plain


def test_pruned_item_formatter_to_json_serializable() -> None:
    formatter = PrunedItemFormatter()
    item = PrunedItem(
        category=StaleSandboxCategory.STALE_BRANCH,
        identifier="feature/1",
        action=PruneAction.PRUNED,
        reason="Would prune",
    )
    dumped = formatter.to_json_serializable(item)
    assert dumped["identifier"] == "feature/1"
    assert dumped["category"] == "stale_branch"
    assert dumped["action"] == "pruned"


def test_sandbox_show_formatter_to_rich() -> None:
    formatter = SandboxShowFormatter()
    record = SandboxRecord(
        id="sbx_test1234",
        name="test-sandbox",
        branch_name="worktree/sandbox-test",
        base_commit="abc1234",
        sandbox_path="/tmp/sbx_test1234",
        status=SandboxStatus.ACTIVE,
        created_at="2026-08-31T20:00:00Z",
        updated_at="2026-08-31T20:00:00Z",
    )
    res = SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=record,
        disk_present=True,
    )
    rich_out = formatter.to_rich(res)
    assert rich_out is not None
    out = render_rich(rich_out)
    assert "sbx_test1234" in out

    # Not found case
    not_found_res = SandboxShowResult(
        status=SandboxShowStatus.NOT_FOUND,
        errors=["Sandbox 'sbx_missing' not found."],
    )
    not_found_rich = formatter.to_rich(not_found_res)
    assert not_found_rich is not None
    out_missing = render_rich(not_found_rich)
    assert "Sandbox Not Found" in out_missing


def test_sandbox_show_formatter_to_json_serializable() -> None:
    formatter = SandboxShowFormatter()
    record = SandboxRecord(
        id="sbx_test1234",
        name="test-sandbox",
        branch_name="worktree/sandbox-test",
        base_commit="abc1234",
        sandbox_path="/tmp/sbx_test1234",
        status=SandboxStatus.ACTIVE,
        created_at="2026-08-31T20:00:00Z",
        updated_at="2026-08-31T20:00:00Z",
    )
    res = SandboxShowResult(
        status=SandboxShowStatus.OK,
        sandbox=record,
        disk_present=True,
    )
    dumped = formatter.to_json_serializable(res)
    assert dumped["status"] == "ok"
    assert dumped["sandbox"]["id"] == "sbx_test1234"


def test_sandbox_list_formatter_to_rich() -> None:
    formatter = SandboxListFormatter()
    record = SandboxRecord(
        id="sbx_list1234",
        name="list-sandbox",
        branch_name="worktree/sandbox-list",
        base_commit="abc1234",
        sandbox_path="/tmp/sbx_list1234",
        status=SandboxStatus.ACTIVE,
        created_at="2026-08-31T20:00:00Z",
        updated_at="2026-08-31T20:00:00Z",
    )

    # With items
    res_items = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[record])
    rich_items = formatter.to_rich(res_items)
    assert rich_items is not None
    out_items = render_rich(rich_items)
    assert "sbx_list1234" in out_items

    # Empty list
    res_empty = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[])
    rich_empty = formatter.to_rich(res_empty)
    assert isinstance(rich_empty, Text)
    assert "No sandboxes found." in rich_empty.plain


def test_sandbox_list_formatter_to_json_serializable() -> None:
    formatter = SandboxListFormatter()
    res = SandboxListResult(status=SandboxListStatus.OK, sandboxes=[])
    dumped = formatter.to_json_serializable(res)
    assert dumped["status"] == "ok"
    assert dumped["sandboxes"] == []


def test_sandbox_create_formatter_to_rich() -> None:
    formatter = SandboxCreateFormatter()
    session = SandboxSession(
        session_id="sbx_create123",
        target_branch="worktree/sandbox-create123",
        sandbox_path=Path("/tmp/sbx_create123"),
        base_commit="def5678",
        created_at="2026-08-31T20:00:00Z",
    )

    # Success case
    res_ok = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)
    rich_ok = formatter.to_rich(res_ok)
    assert rich_ok is not None
    out_ok = render_rich(rich_ok)
    assert "sbx_create123" in out_ok

    # Failure case
    res_fail = SandboxCreateResult(
        status=SandboxCreateStatus.GIT_FAILED,
        errors=["Git checkout failed."],
    )
    rich_fail = formatter.to_rich(res_fail)
    assert rich_fail is not None
    out_fail = render_rich(rich_fail)
    assert "Git checkout failed." in out_fail


def test_sandbox_create_formatter_to_json_serializable() -> None:
    formatter = SandboxCreateFormatter()
    session = SandboxSession(
        session_id="sbx_create123",
        target_branch="worktree/sandbox-create123",
        sandbox_path=Path("/tmp/sbx_create123"),
        base_commit="def5678",
        created_at="2026-08-31T20:00:00Z",
    )
    res = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)
    dumped = formatter.to_json_serializable(res)
    assert dumped["status"] == "ok"
    assert dumped["session"]["session_id"] == "sbx_create123"


def test_ui_dispatcher_registrations() -> None:
    """Verify ui_dispatcher has all 8 sandbox formatters registered."""
    from worktree.core.sandbox.models import (
        SandboxApplyResult,
        SandboxDeleteResult,
        SandboxDiffResult,
        SandboxPruneResult,
    )

    assert PrunedItem in ui_dispatcher._registry
    assert SandboxPruneResult in ui_dispatcher._registry
    assert SandboxShowResult in ui_dispatcher._registry
    assert SandboxListResult in ui_dispatcher._registry
    assert SandboxCreateResult in ui_dispatcher._registry
    assert SandboxApplyResult in ui_dispatcher._registry
    assert SandboxDeleteResult in ui_dispatcher._registry
    assert SandboxDiffResult in ui_dispatcher._registry


def test_sandbox_prune_formatter_empty() -> None:
    from worktree.cli.sandbox.formatters import SandboxPruneFormatter
    from worktree.core.sandbox.models import SandboxPruneResult

    formatter = SandboxPruneFormatter()
    res = SandboxPruneResult()
    rich_out = formatter.to_rich(res)
    assert isinstance(rich_out, Text)
    assert "No stale sandboxes found." in rich_out.plain

    dumped = formatter.to_json_serializable(res)
    assert dumped["status"] == "ok"
    assert dumped["items"] == []


def test_sandbox_prune_formatter_with_items() -> None:
    from worktree.cli.sandbox.formatters import SandboxPruneFormatter
    from worktree.core.sandbox.models import SandboxPruneResult

    formatter = SandboxPruneFormatter()
    item = PrunedItem(
        category=StaleSandboxCategory.STALE_BRANCH,
        identifier="feature/1",
        action=PruneAction.PRUNED,
    )
    res = SandboxPruneResult(items=[item], errors=["some error"])
    rich_out = formatter.to_rich(res)
    assert rich_out is not None


def test_dispatcher_json_format_ndjson(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    dispatcher.register(PrunedItem, PrunedItemFormatter())

    item = PrunedItem(
        category=StaleSandboxCategory.STALE_BRANCH,
        identifier="branch-abc",
        action=PruneAction.PRUNED,
        reason="Would prune stale branch",
    )
    dispatcher.dispatch(item, output_format="json")

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "PrunedItem"
    assert parsed["payload"]["identifier"] == "branch-abc"
