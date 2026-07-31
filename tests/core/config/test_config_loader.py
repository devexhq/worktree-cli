"""Tests for config loader, path resolution, and context warnings."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from getworktree.core.config.context import load_context
from getworktree.core.config.generator import (
    build_default_config,
    generate_default_config,
)
from getworktree.core.config.loader import (
    ConfigLoadStatus,
    load_config,
    load_config_result,
    load_raw_config,
    parse_and_validate_config,
    resolve_config_path,
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


def _write_config(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class ResolveConfigPathTests:
    """Tests for resolve_config_path."""

    def test_default_path_is_absolute(self, tmp_path: Path) -> None:
        resolved = resolve_config_path(cwd=tmp_path)
        assert resolved.is_absolute()
        assert resolved == (tmp_path / ".worktree" / "config.json").resolve()

    def test_explicit_path_wins(self, tmp_path: Path) -> None:
        explicit = tmp_path / "custom" / "cfg.json"
        resolved = resolve_config_path(cwd=tmp_path, config_path=explicit)
        assert resolved == explicit.resolve()


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


class LoadConfigResultTests:
    """Tests for load_config_result status classification."""

    def test_ok_after_init(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        result_gen = generate_default_config(config_path, "demo")
        assert result_gen.ok
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.OK
        assert result.ok
        assert result.config_path == config_path.resolve()
        assert result.raw is not None
        assert result.config is not None
        assert result.config.project.name == "demo"
        assert result.errors == []
        # Loader must not mutate the file.
        on_disk = json.loads(config_path.read_text(encoding="utf-8"))
        assert on_disk == result.raw

    def test_not_found(self, tmp_path: Path) -> None:
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.NOT_FOUND
        assert not result.ok
        assert result.config is None
        joined = "\n".join(result.errors)
        assert "wt init" in joined
        assert str(result.config_path) in joined
        assert "CONFIG_NOT_FOUND" in joined

    def test_not_found_missing_parent(self, tmp_path: Path) -> None:
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.NOT_FOUND

    def test_malformed_json(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path / ".worktree" / "config.json", "{not-json")
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.MALFORMED_JSON
        assert any("Malformed" in e for e in result.errors)
        assert any(str(path.resolve()) in e for e in result.errors)

    def test_root_not_object(self, tmp_path: Path) -> None:
        _write_config(tmp_path / ".worktree" / "config.json", [])
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.ROOT_NOT_OBJECT
        assert any("CONFIG_ROOT_NOT_OBJECT" in e for e in result.errors)

    def test_schema_invalid_missing_keys(self, tmp_path: Path) -> None:
        _write_config(tmp_path / ".worktree" / "config.json", {"version": 1})
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID
        assert result.raw == {"version": 1}
        assert result.config is None
        assert result.errors
        assert any("schema validation failed" in e.lower() for e in result.errors)

    def test_schema_invalid_wrong_types(self, tmp_path: Path) -> None:
        raw = build_default_config("demo")
        raw["loop"]["default_max_attempts"] = "five"
        _write_config(tmp_path / ".worktree" / "config.json", raw)
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID

    def test_schema_invalid_wrong_version(self, tmp_path: Path) -> None:
        raw = build_default_config("demo")
        raw["version"] = 2
        _write_config(tmp_path / ".worktree" / "config.json", raw)
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID

    def test_path_is_directory(self, tmp_path: Path) -> None:
        path = tmp_path / ".worktree" / "config.json"
        path.mkdir(parents=True)
        result = load_config_result(cwd=tmp_path)
        assert result.status == ConfigLoadStatus.PATH_IS_DIRECTORY
        assert any("CONFIG_PATH_IS_DIRECTORY" in e for e in result.errors)

    def test_unreadable(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path / ".worktree" / "config.json",
            build_default_config("demo"),
        )
        path.chmod(0)
        try:
            result = load_config_result(cwd=tmp_path)
            # Some environments (e.g. root) may still read the file.
            if os.access(path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            assert result.status == ConfigLoadStatus.UNREADABLE
            assert any("CONFIG_UNREADABLE" in e for e in result.errors)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_explicit_config_path(self, tmp_path: Path) -> None:
        alt = tmp_path / "elsewhere" / "config.json"
        alt.parent.mkdir(parents=True)
        assert generate_default_config(alt, "alt-demo").ok
        result = load_config_result(cwd=tmp_path, config_path=alt)
        assert result.ok
        assert result.config is not None
        assert result.config.project.name == "alt-demo"
        assert result.config_path == alt.resolve()


class LoadConfigRaisingHelpersTests:
    """Tests for raising wrappers over load_config_result."""

    def test_load_config_ok(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "demo").ok
        config = load_config(cwd=tmp_path)
        assert config.project.name == "demo"

    def test_load_config_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="wt init"):
            load_config(cwd=tmp_path)

    def test_load_raw_config_object_required(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text("[]\n", encoding="utf-8")
        with pytest.raises(ValueError, match="object"):
            load_raw_config(path)

    def test_load_raw_config_malformed_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text("{bad", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed"):
            load_raw_config(path)


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
