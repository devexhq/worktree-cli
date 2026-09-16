from __future__ import annotations

from pathlib import Path

import pytest

from worktree.core.agents.mutation_git import (
    capture_diff_since,
    discard_since,
    resolve_pre_agent_baseline,
)

pytestmark = pytest.mark.integration


class DirectMutationGitSafetyTests:
    """Integration tests verifying pre-agent WIP preservation during direct mutation rollbacks."""

    def test_mutation_git_preserves_wip_baseline_when_agent_discards_changes(
        self,
        git_repo: Path,
    ) -> None:
        """Rollback restores pre-existing uncommitted WIP files and discards agent edits."""
        readme_file = git_repo / "README.md"
        readme_file.write_text("# Test Repo\nUncommitted WIP edit in README\n", encoding="utf-8")

        wip_file = git_repo / "feature_wip.py"
        wip_file.write_text("print('uncommitted WIP code')\n", encoding="utf-8")

        baseline = resolve_pre_agent_baseline(git_repo)

        readme_file.write_text("# Test Repo\nAgent corrupted README\n", encoding="utf-8")
        wip_file.write_text("print('agent modified this file')\n", encoding="utf-8")
        agent_junk = git_repo / "agent_garbage.tmp"
        agent_junk.write_text("agent temporary junk\n", encoding="utf-8")

        agent_diff, agent_touched = capture_diff_since(git_repo, baseline)
        assert agent_diff != ""
        assert agent_touched == ["README.md", "agent_garbage.tmp", "feature_wip.py"]

        discard_since(git_repo, baseline)

        assert readme_file.read_text(encoding="utf-8") == "# Test Repo\nUncommitted WIP edit in README\n"
        assert wip_file.read_text(encoding="utf-8") == "print('uncommitted WIP code')\n"
        assert agent_junk.exists() is False

        post_discard_diff, post_discard_touched = capture_diff_since(git_repo, baseline)
        assert post_discard_diff == ""
        assert post_discard_touched == []
