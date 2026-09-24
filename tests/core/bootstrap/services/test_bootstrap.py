"""Contract tests for worktree.core.bootstrap.services.bootstrap.bootstrap_worktree."""

from __future__ import annotations

from pathlib import Path

from worktree.common.constants import WORKTREE_GITIGNORE_CONTENT
from worktree.core.bootstrap.services.bootstrap import bootstrap_worktree


class BootstrapWorktreeTests:
    """Contract tests for bootstrap_worktree's directory trimming and local .gitignore seeding."""

    def test_bootstrap_worktree_fresh_root_creates_gitignore_with_expected_content(self, tmp_path: Path) -> None:
        """bootstrap_worktree: fresh root creates only .meta/ and writes .worktree/.gitignore matching WORKTREE_GITIGNORE_CONTENT exactly, result.gitignore_created=True."""
        root_path = tmp_path / ".worktree"

        result = bootstrap_worktree(root_path)

        assert result.gitignore_created is True
        assert result.dirs_created == [result.root_path / ".meta"]
        assert (result.root_path / ".gitignore").read_text(encoding="utf-8") == WORKTREE_GITIGNORE_CONTENT

    def test_bootstrap_worktree_rerun_preserves_existing_gitignore(self, tmp_path: Path) -> None:
        """bootstrap_worktree: rerun on a root with a user-edited .gitignore returns gitignore_created=False and leaves its content untouched."""
        root_path = tmp_path / ".worktree"
        first_result = bootstrap_worktree(root_path)
        custom_content = "sandboxes/\ncustom-entry\n"
        (first_result.root_path / ".gitignore").write_text(custom_content, encoding="utf-8")

        result = bootstrap_worktree(root_path)

        assert result.gitignore_created is False
        assert (result.root_path / ".gitignore").read_text(encoding="utf-8") == custom_content
