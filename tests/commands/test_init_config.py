"""Integration tests for wt init config generation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from getworktree.commands.init import init_command
from importlib import resources

from getworktree.common.schema_validation import SchemaValidator

CONFIG_VALIDATOR = SchemaValidator(resources.files("getworktree.schemas") / "config_v1.json")


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


def test_init_creates_v1_config(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(git_repo)
    init_command(tool_version="0.1.1")

    config_path = git_repo / ".worktree" / "config.json"
    assert config_path.is_file()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["project"]["name"] == git_repo.name
    assert CONFIG_VALIDATOR.validate(data).ok


def test_init_idempotent_config(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(git_repo)
    init_command(tool_version="0.1.1")
    config_path = git_repo / ".worktree" / "config.json"
    first = config_path.read_text(encoding="utf-8")

    init_command(tool_version="0.1.1")
    second = config_path.read_text(encoding="utf-8")
    assert first == second


def test_init_repair_partial_config(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
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
