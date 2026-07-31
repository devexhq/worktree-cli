"""Tests for Git sandbox lifecycle."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from getworktree.core.config.generator import generate_default_config
from getworktree.core.git_sandbox import GitSandboxManager, sandbox_scope


def _init_git_repo(path: Path, branch: str = "feature") -> None:
    subprocess.run(
        ["git", "init", "-b", branch], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    wt = tmp_path / ".worktree"
    wt.mkdir()
    generate_default_config(wt / "config.json", tmp_path.name)
    return tmp_path


class GitSandboxManagerTests:
    """Integration tests against a real git repository."""

    def test_create_and_cleanup(self, repo: Path) -> None:
        manager = GitSandboxManager(cwd=repo)
        session = manager.create_sandbox(session_id="sbx_test1")
        assert session.sandbox_path.is_dir()
        assert (session.sandbox_path / "f.txt").is_file()
        manager.cleanup_sandbox(session)
        assert not session.sandbox_path.exists()

    def test_max_active_enforced(self, repo: Path) -> None:
        config_path = repo / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["max_active_sandboxes"] = 1
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        manager = GitSandboxManager(cwd=repo)
        first = manager.create_sandbox(session_id="sbx_a")
        with pytest.raises(RuntimeError, match="Maximum active"):
            manager.create_sandbox(session_id="sbx_b")
        manager.cleanup_sandbox(first)

    def test_sandbox_scope_auto_clean_on_success(self, repo: Path) -> None:
        with sandbox_scope(cwd=repo, session_id="sbx_scope") as session:
            session.command_passed = True
            path = session.sandbox_path
            assert path.is_dir()
        assert not path.exists()

    def test_keep_on_failure(self, repo: Path) -> None:
        with sandbox_scope(cwd=repo, session_id="sbx_fail") as session:
            session.command_passed = False
            path = session.sandbox_path
        assert path.exists()
        # manual cleanup for tmp dir hygiene
        GitSandboxManager(cwd=repo).cleanup_sandbox(
            type(session)(
                session_id=session.session_id,
                target_branch=session.target_branch,
                sandbox_path=path,
                created_at=session.created_at,
            )
        )
