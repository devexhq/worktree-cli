"""Tests for config loader, path resolution, and context warnings."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.config.generator import (
    build_default_config,
    generate_default_config,
)
from worktree.core.config.loader import (
    ConfigLoadStatus,
    clear_config_cache,
    load_config,
    parse_and_validate_config,
    resolve_config_path,
)


def _write_config(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class ResolveConfigPathTests:
    """Tests for resolve_config_path."""

    def test_default_path_is_absolute(self, fs: FileSystem) -> None:
        resolved = resolve_config_path(path=fs.base_path)
        assert resolved.is_absolute()
        assert resolved == (fs.base_path / ".worktree" / "config.json").resolve()

    def test_explicit_path_wins(self, fs: FileSystem) -> None:
        explicit = fs.base_path / "custom" / "cfg.json"
        resolved = resolve_config_path(path=fs.base_path, config_path=explicit)
        assert resolved == explicit.resolve()

    def test_omitted_path_does_not_raise(self) -> None:
        resolved = resolve_config_path()
        assert resolved.is_absolute()
        assert resolved.name == "config.json"


class ParseAndValidateConfigTests:
    """Tests for parse_and_validate_config."""

    def test_round_trip_from_defaults(self) -> None:
        raw = build_default_config("demo")
        config = parse_and_validate_config(raw)
        assert config.version == 1
        assert config.project.name == "demo"
        assert config.paths.db_path == ".worktree/data.db"
        assert config.sandbox.max_active_sandboxes == 3
        assert config.agent.provider == "local"
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


class LoadConfigTests:
    """Tests for load_config status classification and caching."""

    def test_ok_after_init(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        result_gen = generate_default_config(config_path, "demo")
        assert result_gen.ok
        result = load_config(path=fs.base_path)
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

    def test_not_found(self, fs: FileSystem) -> None:
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.NOT_FOUND
        assert not result.ok
        assert result.config is None
        joined = "\n".join(result.errors)
        assert "wt init" in joined
        assert str(result.config_path) in joined
        assert "CONFIG_NOT_FOUND" in joined

    def test_zero_arguments_does_not_raise(self) -> None:
        result = load_config()
        assert result.status in (ConfigLoadStatus.OK, ConfigLoadStatus.NOT_FOUND)
        assert result.config_path.name == "config.json"

    def test_not_found_missing_parent(self, fs: FileSystem) -> None:
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.NOT_FOUND

    def test_malformed_json(self, fs: FileSystem) -> None:
        path = _write_config(fs.base_path / ".worktree" / "config.json", "{not-json")
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.MALFORMED_JSON
        assert any("Malformed" in e for e in result.errors)
        assert any(str(path.resolve()) in e for e in result.errors)

    def test_root_not_object(self, fs: FileSystem) -> None:
        _write_config(fs.base_path / ".worktree" / "config.json", [])
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.ROOT_NOT_OBJECT
        assert any("CONFIG_ROOT_NOT_OBJECT" in e for e in result.errors)

    def test_schema_invalid_missing_keys(self, fs: FileSystem) -> None:
        _write_config(fs.base_path / ".worktree" / "config.json", {"version": 1})
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID
        assert result.raw == {"version": 1}
        assert result.config is None
        assert result.errors
        assert any("schema validation failed" in e.lower() for e in result.errors)

    def test_schema_invalid_wrong_types(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["sandbox"]["max_active_sandboxes"] = "five"
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID

    def test_schema_invalid_wrong_version(self, fs: FileSystem) -> None:
        raw = build_default_config("demo")
        raw["version"] = 2
        _write_config(fs.base_path / ".worktree" / "config.json", raw)
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.SCHEMA_INVALID

    def test_path_is_directory(self, fs: FileSystem) -> None:
        path = fs.base_path / ".worktree" / "config.json"
        path.mkdir(parents=True)
        result = load_config(path=fs.base_path)
        assert result.status == ConfigLoadStatus.PATH_IS_DIRECTORY
        assert any("CONFIG_PATH_IS_DIRECTORY" in e for e in result.errors)

    def test_unreadable(self, fs: FileSystem) -> None:
        path = _write_config(
            fs.base_path / ".worktree" / "config.json",
            build_default_config("demo"),
        )
        path.chmod(0)
        try:
            result = load_config(path=fs.base_path)
            # Some environments (e.g. root) may still read the file.
            if os.access(path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            assert result.status == ConfigLoadStatus.UNREADABLE
            assert any("CONFIG_UNREADABLE" in e for e in result.errors)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_explicit_config_path(self, fs: FileSystem) -> None:
        alt = fs.base_path / "elsewhere" / "config.json"
        alt.parent.mkdir(parents=True)
        assert generate_default_config(alt, "alt-demo").ok
        result = load_config(path=fs.base_path, config_path=alt)
        assert result.ok
        assert result.config is not None
        assert result.config.project.name == "alt-demo"
        assert result.config_path == alt.resolve()

    def test_cache_hit_on_unmodified_file(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "cache-demo").ok
        res1 = load_config(path=fs.base_path)
        res2 = load_config(path=fs.base_path)
        assert res1 is res2

    def test_cache_invalidated_on_file_edit(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "cache-demo").ok
        res1 = load_config(path=fs.base_path)
        assert res1.config is not None
        assert res1.config.project.name == "cache-demo"

        # Modify file on disk with a new project name and new timestamp
        raw = build_default_config("modified-demo")
        _write_config(config_path, raw)

        res2 = load_config(path=fs.base_path)
        assert res2.config is not None
        assert res2.config.project.name == "modified-demo"
        assert res2 is not res1

    def test_clear_config_cache(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "cache-demo").ok
        res1 = load_config(path=fs.base_path)
        clear_config_cache(fs.base_path)
        res2 = load_config(path=fs.base_path)
        assert res1 is not res2
        assert res2.config is not None
        assert res2.config.project.name == "cache-demo"
