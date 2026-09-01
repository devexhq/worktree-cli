"""Tests for Config domain facade."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.config import Config


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
