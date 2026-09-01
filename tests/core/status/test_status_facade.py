"""Tests for Status domain facade."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.status import Status, WorktreeStatusResult


def test_status_facade_collect(git_fs: GitFileSystem):
    git_fs.init_repo()
    status = Status(git_fs.base_path)
    result = status.collect()
    assert isinstance(result, WorktreeStatusResult)
    assert result.git.is_git_repo

    classmethod_res = Status.collect_at(git_fs.base_path)
    assert isinstance(classmethod_res, WorktreeStatusResult)
    assert classmethod_res.git.is_git_repo
