"""Tests for sandbox-only git baseline/capture/discard helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from getworktree.core.workflows.agents.mutation_git import (
    MutationGitError,
    capture_diff_since,
    discard_since,
    resolve_pre_agent_baseline,
)


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    _git(["init"], cwd=root)
    _git(["config", "user.email", "test@example.com"], cwd=root)
    _git(["config", "user.name", "Test"], cwd=root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], cwd=root)
    _git(["commit", "-m", "init"], cwd=root)
    return root


class ResolvePreAgentBaselineTests:
    def test_clean_tree_baselines_to_head(self, repo: Path) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        baseline = resolve_pre_agent_baseline(repo)

        assert baseline == head

    def test_dirty_tree_creates_marker_commit(self, repo: Path) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        (repo / "a.txt").write_text("wip change\n", encoding="utf-8")

        baseline = resolve_pre_agent_baseline(repo)

        assert baseline != head
        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert log == "wt: pre-agent baseline"
        assert (repo / "a.txt").read_text(encoding="utf-8") == "wip change\n"

    def test_raises_on_git_failure(self, tmp_path: Path) -> None:
        not_a_repo = tmp_path / "not-a-repo"
        not_a_repo.mkdir()
        with pytest.raises(MutationGitError):
            resolve_pre_agent_baseline(not_a_repo)

    def test_raises_on_git_timeout(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import getworktree.core.workflows.agents.mutation_git as mutation_mod

        def _timeout(*_args: object, **_kwargs: object) -> object:
            raise subprocess.TimeoutExpired(cmd=["git"], timeout=120)

        monkeypatch.setattr(mutation_mod.subprocess, "run", _timeout)
        with pytest.raises(MutationGitError, match="GIT_TIMEOUT"):
            resolve_pre_agent_baseline(repo)


class CaptureDiffSinceTests:
    def test_captures_modified_and_new_files(self, repo: Path) -> None:
        baseline = resolve_pre_agent_baseline(repo)
        (repo / "a.txt").write_text("agent edit\n", encoding="utf-8")
        (repo / "b.txt").write_text("new file\n", encoding="utf-8")

        diff, touched = capture_diff_since(repo, baseline)

        assert touched == ["a.txt", "b.txt"]
        assert "agent edit" in diff
        assert "new file" in diff

    def test_captures_agent_own_commits(self, repo: Path) -> None:
        baseline = resolve_pre_agent_baseline(repo)
        (repo / "a.txt").write_text("committed by agent\n", encoding="utf-8")
        _git(["add", "-A"], cwd=repo)
        _git(["commit", "-m", "agent commit"], cwd=repo)

        diff, touched = capture_diff_since(repo, baseline)

        assert touched == ["a.txt"]
        assert "committed by agent" in diff

    def test_empty_diff_when_no_changes(self, repo: Path) -> None:
        baseline = resolve_pre_agent_baseline(repo)

        diff, touched = capture_diff_since(repo, baseline)

        assert diff == ""
        assert touched == []


class DiscardSinceTests:
    def test_discards_agent_edits_on_clean_baseline(self, repo: Path) -> None:
        baseline = resolve_pre_agent_baseline(repo)
        (repo / "a.txt").write_text("bad agent edit\n", encoding="utf-8")
        (repo / "junk.txt").write_text("untracked\n", encoding="utf-8")

        discard_since(repo, baseline)

        assert (repo / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (repo / "junk.txt").exists()

    def test_discard_preserves_wip_baseline(self, repo: Path) -> None:
        (repo / "a.txt").write_text("wip content\n", encoding="utf-8")
        baseline = resolve_pre_agent_baseline(repo)
        (repo / "a.txt").write_text("agent overwrote wip\n", encoding="utf-8")

        discard_since(repo, baseline)

        # Discard must restore the WIP overlay, not the original committed tip.
        assert (repo / "a.txt").read_text(encoding="utf-8") == "wip content\n"

    def test_raises_on_git_failure(self, repo: Path) -> None:
        with pytest.raises(MutationGitError):
            discard_since(repo, "not-a-real-ref")
