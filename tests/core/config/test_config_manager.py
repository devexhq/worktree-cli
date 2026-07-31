"""Tests for config manager load/validate/context warnings."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from getworktree.core.config.generator import (
    build_default_config,
    generate_default_config,
)
from getworktree.core.config.manager import (
    load_context,
    load_raw_config,
    parse_and_validate_config,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "f.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


class ParseAndValidateConfigTests:
    """Tests for parse_and_validate_config."""

    def test_round_trip_from_defaults(self) -> None:
        raw = build_default_config("demo")
        config = parse_and_validate_config(raw)
        assert config.version == 1
        assert config.project.name == "demo"
        assert config.paths.db_path == ".worktree/token_audit.db"
        assert config.loop.default_max_attempts == 5
        assert config.patch.max_files == 30
        assert config.approval.require_before_apply is True
        assert config.history.max_sessions == 1000
        assert config.doctor.check_git is True
        assert config.prune.artifact_ttl_days == 30
        assert config.telemetry.enabled is False

    def test_null_project_name_becomes_unnamed(self) -> None:
        raw = build_default_config("demo")
        raw["project"]["name"] = None
        config = parse_and_validate_config(raw)
        assert config.project.name == "unnamed_project"

    def test_invalid_schema_raises(self) -> None:
        with pytest.raises(ValueError, match="schema validation failed"):
            parse_and_validate_config({"version": 1})


class LoadContextTests:
    """Tests for load_context and warnings."""

    def test_missing_config_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_context(tmp_path)

    def test_invalid_json_raises(self, git_repo: Path) -> None:
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{not-json", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed"):
            load_context(git_repo)

    def test_warnings_for_main_and_missing_model(self, git_repo: Path) -> None:
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        generate_default_config(config_path, git_repo.name)
        ctx = load_context(git_repo)
        assert any("agent.model" in w for w in ctx.warnings)
        assert any("main" in w for w in ctx.warnings)

    def test_load_raw_config_object_required(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text("[]\n", encoding="utf-8")
        with pytest.raises(ValueError, match="object"):
            load_raw_config(path)
