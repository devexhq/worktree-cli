from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from worktree.common.filesystem import Filesystem
from worktree.core.config.exceptions import ConfigLoadError
from worktree.core.config.facade import Config
from worktree.core.config.generator import build_default_config
from worktree.core.config.models import ConfigTier


class ConfigLoadTests:
    """[tier-1/unit] Config.load() routing contract."""

    def test_load_reflects_user_tier_override(
        self, isolated_workspace: Path, write_tier_config: Callable[[ConfigTier, dict[str, Any] | str], Path]
    ) -> None:
        """[tier-1/unit] Config.load: User tier agent.model override is present on the returned ConfigLoadResult.config."""
        write_tier_config(ConfigTier.USER, {"agent": {"model": "user-tier-model"}})
        Filesystem.atomic_write_json(
            isolated_workspace / ".worktree" / "config.json",
            {"version": 1, "project": {"name": "demo-workspace"}},
        )

        result = Config(isolated_workspace).load()

        assert result.config is not None
        assert result.config.agent.model == "user-tier-model"


class ConfigLoadedConfigAccessorTests:
    """[tier-1/unit] Config._loaded_config exception contract (NFR-2)."""

    def test_loaded_config_raises_config_load_error_for_tier_invalid_status(
        self, isolated_workspace: Path, write_tier_config: Callable[[ConfigTier, dict[str, Any] | str], Path]
    ) -> None:
        """[tier-1/unit] Config._loaded_config: malformed User tier → raises ConfigLoadError whose message contains the tier-attributed detail text."""
        write_tier_config(ConfigTier.USER, "{not valid json")
        Filesystem.atomic_write_json(
            isolated_workspace / ".worktree" / "config.json", build_default_config("demo-workspace")
        )

        with pytest.raises(ConfigLoadError, match="Invalid configuration in user layer"):
            _ = Config(isolated_workspace)._loaded_config
