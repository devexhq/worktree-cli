"""Tests for `getworktree.core.config.generator`."""

from __future__ import annotations

import json
import os
import stat
from importlib import resources
from pathlib import Path

import pytest

from getworktree.common.fs import atomic_write_json
from getworktree.common.schema_validation import SchemaValidator
from getworktree.core.config.generator import (
    CANONICAL_V1_DEFAULTS,
    build_default_config,
    generate_default_config,
    merge_missing_keys,
)

CONFIG_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas.v1") / "config.json"
)


@pytest.fixture
def project_tmp(tmp_path: Path) -> Path:
    return tmp_path


class BuildDefaultConfigTests:
    """Tests for `build_default_config`."""

    def test_build_default_config_sets_runtime_fields(self):
        config = build_default_config("my-repo")
        assert config["version"] == 1
        assert config["project"]["name"] == "my-repo"
        assert config["project"]["initialized_at"]
        validation = CONFIG_VALIDATOR.validate(config)
        assert validation.ok

    def test_canonical_defaults_validate(self):
        config = build_default_config("x")
        validation = CONFIG_VALIDATOR.validate(config)
        assert validation.ok, validation.errors


class GenerateDefaultConfigTests:
    """Tests for `generate_default_config`."""

    def test_creates_config_when_missing(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)

        result = generate_default_config(config_path, "demo")
        assert result.ok
        assert result.created
        assert not result.skipped_existing
        assert config_path.is_file()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["project"]["name"] == "demo"
        assert CONFIG_VALIDATOR.validate(data).ok

    def test_skips_when_existing(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        original = build_default_config("first")
        atomic_write_json(config_path, original)

        result = generate_default_config(config_path, "second")
        assert result.ok
        assert result.skipped_existing
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["project"]["name"] == "first"

    def test_skips_invalid_json_without_repair(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{not json", encoding="utf-8")

        result = generate_default_config(config_path, "demo")
        assert result.ok
        assert result.skipped_existing
        assert config_path.read_text(encoding="utf-8") == "{not json"

    def test_overwrite_replaces_existing(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        stale = build_default_config("old")
        stale["custom_key"] = True
        atomic_write_json(config_path, stale)

        result = generate_default_config(config_path, "new", overwrite=True)
        assert result.ok
        assert result.overwritten
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["project"]["name"] == "new"
        assert "custom_key" not in data

    def test_repair_inserts_missing_keys(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        partial = {
            "version": 1,
            "project": {
                "name": "keep-me",
                "initialized_at": "2020-01-01T00:00:00+00:00",
            },
            "paths": CANONICAL_V1_DEFAULTS["paths"],
            "sandbox": {"auto_clean": False, "max_active_sandboxes": 2},
        }
        atomic_write_json(config_path, partial)

        result = generate_default_config(config_path, "ignored", repair=True)
        assert result.ok
        assert result.repaired
        assert result.inserted_keys
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["project"]["name"] == "keep-me"
        assert data["sandbox"]["auto_clean"] is False
        assert data["workflow"]["default_max_attempts"] == 5
        assert CONFIG_VALIDATOR.validate(data).ok

    def test_repair_invalid_json_errors(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{bad", encoding="utf-8")

        result = generate_default_config(config_path, "demo", repair=True)
        assert not result.ok
        assert any("CONFIG_INVALID_JSON" in e for e in result.errors)

    def test_config_path_is_directory(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.mkdir(parents=True)

        result = generate_default_config(config_path, "demo")
        assert not result.ok
        assert any("CONFIG_PATH_IS_DIRECTORY" in e for e in result.errors)

    def test_unwritable_parent(self, project_tmp: Path):
        worktree = project_tmp / ".worktree"
        worktree.mkdir()
        os.chmod(worktree, stat.S_IRUSR | stat.S_IXUSR)
        config_path = worktree / "config.json"

        result = generate_default_config(config_path, "demo")
        assert not result.ok
        assert any("CONFIG_PATH_NOT_WRITABLE" in e for e in result.errors)

        os.chmod(worktree, stat.S_IRWXU)

    def test_parent_missing(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"

        result = generate_default_config(config_path, "demo")
        assert not result.ok
        assert any("CONFIG_PARENT_MISSING" in e for e in result.errors)

    def test_overwrite_ignores_repair_with_warning(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        atomic_write_json(config_path, build_default_config("old"))

        result = generate_default_config(
            config_path, "new", overwrite=True, repair=True
        )
        assert result.ok
        assert result.overwritten
        assert any("repair ignored" in w for w in result.warnings)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["project"]["name"] == "new"

    def test_repair_non_object_json_errors(self, project_tmp: Path):
        config_path = project_tmp / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("[1, 2, 3]\n", encoding="utf-8")

        result = generate_default_config(config_path, "demo", repair=True)
        assert not result.ok
        assert any("CONFIG_INVALID_JSON" in e for e in result.errors)


class AtomicWriteJsonTests:
    """Tests for `atomic_write_json` as used by config generation."""

    def test_atomic_write_no_temp_file(self, project_tmp: Path):
        target = project_tmp / "config.json"
        atomic_write_json(target, build_default_config("x"))
        assert target.is_file()
        assert not (project_tmp / "config.json.tmp").exists()
        assert target.read_text(encoding="utf-8").endswith("\n")


class MergeMissingKeysTests:
    """Tests for `merge_missing_keys`."""

    def test_merge_missing_keys_nested(self):
        existing = {"a": {"b": 1}}
        defaults = {"a": {"b": 9, "c": 2}, "d": 3}
        inserted = merge_missing_keys(existing, defaults)
        assert "a.c" in inserted
        assert "d" in inserted
        assert existing["a"]["b"] == 1
        assert existing["a"]["c"] == 2
