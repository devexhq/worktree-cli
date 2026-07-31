"""Integration tests for `getworktree.commands.init.command.init_command`."""

from __future__ import annotations

import json
import subprocess
from importlib import resources
from pathlib import Path

import pytest

from getworktree.commands.init import init_command
from getworktree.common.schema_validation import SchemaValidator

CONFIG_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas") / "config_v1.json"
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


class InitCommandConfigTests:
    """Tests for config generation behavior triggered by `wt init`."""

    def test_init_creates_v1_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(git_repo)
        init_command(tool_version="0.1.1")

        config_path = git_repo / ".worktree" / "config.json"
        assert config_path.is_file()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["project"]["name"] == git_repo.name
        assert CONFIG_VALIDATOR.validate(data).ok

    def test_init_idempotent_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(git_repo)
        init_command(tool_version="0.1.1")
        config_path = git_repo / ".worktree" / "config.json"
        first = config_path.read_text(encoding="utf-8")

        init_command(tool_version="0.1.1")
        second = config_path.read_text(encoding="utf-8")
        assert first == second

    def test_init_repair_partial_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(git_repo)
        init_command(tool_version="0.1.1")
        config_path = git_repo / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        del data["telemetry"]
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        init_command(tool_version="0.1.1", repair=True)
        repaired = json.loads(config_path.read_text(encoding="utf-8"))
        assert "telemetry" in repaired
        assert CONFIG_VALIDATOR.validate(repaired).ok


class InitCommandLoopSeedingTests:
    """Tests for starter loop seeding behavior triggered by `wt init`."""

    def test_init_seeds_starter_loops_in_fresh_repo(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)

        init_command(tool_version="0.1.1")

        loops_dir = git_repo / ".worktree" / "loops"
        assert (loops_dir / "fix-tests.yml").is_file()
        assert (loops_dir / "review-fix.yml").is_file()

    def test_init_does_not_overwrite_edited_loop_files(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)

        init_command(tool_version="0.1.1")
        loop_path = git_repo / ".worktree" / "loops" / "fix-tests.yml"
        loop_path.write_text("edited by user\n", encoding="utf-8")

        init_command(tool_version="0.1.1")

        assert loop_path.read_text(encoding="utf-8") == "edited by user\n"
