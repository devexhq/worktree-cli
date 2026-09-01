"""Tests for Diff domain facade."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.diff import Diff, DiffStatus


def test_diff_facade_inspect(git_fs: GitFileSystem):
    git_fs.init_repo()
    diff = Diff(git_fs.base_path)

    # Missing session
    missing_res = diff.inspect(session_id="nonexistent-sess")
    assert not missing_res.ok
    assert missing_res.status == DiffStatus.SESSION_NOT_FOUND

    # Create session artifact
    sess_dir = Diff.session_dir(git_fs.base_path, "test-sess-1")
    sess_dir.mkdir(parents=True, exist_ok=True)
    patch_path = Diff.write(sess_dir, "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n")
    assert patch_path.is_file()

    inspect_res = diff.inspect(session_id="test-sess-1")
    assert inspect_res.ok
    assert inspect_res.status == DiffStatus.OK
    assert inspect_res.diff_text is not None
    assert "+new" in inspect_res.diff_text
