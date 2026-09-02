"""Tests for Config domain facade."""

from __future__ import annotations

import pytest

from tests.helpers import FileSystem
from worktree.core.config import Config, ConfigLoadError
from worktree.core.config.models import (
    AgentConfig,
    ConcurrencyConfig,
    DoctorConfig,
    HistoryConfig,
    PathsConfig,
    PruneConfig,
    SandboxConfig,
    TelemetryConfig,
)


def test_config_facade_generate_load_set_validate(fs: FileSystem):
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)

    # generate
    gen_res = config.generate()
    assert gen_res.ok
    assert gen_res.created

    # load
    load_res = config.load()
    assert load_res.ok
    assert load_res.config is not None

    # set
    set_res = config.set("agent.model", "gpt-4o")
    assert set_res.ok
    assert set_res.value == "gpt-4o"

    # validate
    val_res = config.validate()
    assert val_res.ok

    # static helpers
    assert Config.parse_value("123") == 123
    assert Config.parse_value("true") is True
    dumped = Config.dump(load_res.config)
    assert "version" in dumped

    # classmethod helpers
    assert Config.load_from(fs.base_path).ok
    assert Config.validate_at(fs.base_path).ok
    assert Config.set_value(fs.base_path, "agent.model", "claude-3-5").ok


def test_config_accessor_project(fs: FileSystem):
    """Config.project returns the loaded ProjectConfig with the correct name."""
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)
    config.generate()
    assert config.project.name == fs.base_path.name


def test_config_accessor_paths(fs: FileSystem):
    """Config.paths returns the loaded PathsConfig with the default db path."""
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)
    config.generate()
    assert config.paths.db_path == ".worktree/data.db"


def test_config_accessor_version(fs: FileSystem):
    """Config.version returns the integer schema version from the loaded config."""
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)
    config.generate()
    assert config.version == 1


def test_config_accessor_caches_on_repeated_access(fs: FileSystem):
    """Config accessor only loads config once; repeated access returns the same object."""
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)
    config.generate()
    project_first = config.project
    project_second = config.project
    assert project_first is project_second


def test_config_accessor_raises_on_missing_config(fs: FileSystem):
    """Config accessor raises ConfigLoadError when config.json is absent."""
    config = Config(fs.base_path)
    with pytest.raises(ConfigLoadError):
        _ = config.project


def test_config_accessor_all_sections(fs: FileSystem):
    """All section accessor properties return the expected sub-model types."""
    (fs.base_path / ".worktree").mkdir(parents=True, exist_ok=True)
    config = Config(fs.base_path)
    config.generate()
    assert isinstance(config.paths, PathsConfig)
    assert isinstance(config.agent, AgentConfig)
    assert isinstance(config.sandbox, SandboxConfig)
    assert isinstance(config.history, HistoryConfig)
    assert isinstance(config.doctor, DoctorConfig)
    assert isinstance(config.prune, PruneConfig)
    assert isinstance(config.telemetry, TelemetryConfig)
    assert isinstance(config.concurrency, ConcurrencyConfig)
