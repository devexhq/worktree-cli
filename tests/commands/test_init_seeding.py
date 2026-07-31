from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from getworktree.commands.init import init_command


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    return tmp_path


def test_init_seeds_starter_loops_in_fresh_repo(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)

    init_command(tool_version="0.1.1")

    loops_dir = git_repo / ".worktree" / "loops"
    assert (loops_dir / "fix-tests.yml").is_file()
    assert (loops_dir / "review-fix.yml").is_file()


def test_init_does_not_overwrite_edited_loop_files(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)

    init_command(tool_version="0.1.1")
    loop_path = git_repo / ".worktree" / "loops" / "fix-tests.yml"
    loop_path.write_text("edited by user\n", encoding="utf-8")

    init_command(tool_version="0.1.1")

    assert loop_path.read_text(encoding="utf-8") == "edited by user\n"
