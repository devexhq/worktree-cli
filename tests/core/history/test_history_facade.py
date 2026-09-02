"""Tests for History domain facade."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.db import BlueprintKind, RunsRepository, RunStatus
from worktree.core.history import History, HistoryListStatus, HistoryShowStatus


def test_history_facade_list_and_show(git_fs: GitFileSystem):
    git_fs.init_repo()
    db = RunsRepository(git_fs.base_path)
    history = History(git_fs.base_path, db=db)

    # empty list
    list_res = history.list()
    assert list_res.ok
    assert list_res.status == HistoryListStatus.OK
    assert len(list_res.runs) == 0

    # insert a run
    db.create(
        session_id="test-session-123",
        blueprint_name="my-workflow",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
    )

    list_res_after = history.list(kind="workflow", status="completed")
    assert list_res_after.ok
    assert len(list_res_after.runs) == 1
    assert list_res_after.runs[0].session_id == "test-session-123"

    show_res = history.show("test-session-123")
    assert show_res.ok
    assert show_res.status == HistoryShowStatus.OK
    assert show_res.run is not None
    assert show_res.run.session_id == "test-session-123"

    show_missing = history.show("non-existent")
    assert not show_missing.ok
    assert show_missing.status == HistoryShowStatus.NOT_FOUND
