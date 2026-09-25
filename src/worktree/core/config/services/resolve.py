"""Resolve the effective configuration Config and wt config show both read."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem import Filesystem
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus, load_config
from worktree.core.config.services.hierarchical_loader import load_hierarchical_config


def resolve_effective_config(
    path: Path | None = None,
    *,
    config_path: Path | None = None,
) -> ConfigLoadResult:
    """Load the repo tier, then merge Global and User tier overrides on top; never raises."""
    repo_result = load_config(path=path, config_path=config_path)
    if not repo_result.ok:
        return repo_result

    # Mirrors load_config's own no-arg discovery; Config.load always passes a path today.
    repo_root = path if path is not None else Filesystem().root_dir
    hierarchical = load_hierarchical_config(repo_root, None)

    if not hierarchical.ok or hierarchical.config is None:
        return ConfigLoadResult(
            status=ConfigLoadStatus.TIER_INVALID,
            config_path=hierarchical.path or repo_result.config_path,
            errors=list(hierarchical.errors),
        )

    return ConfigLoadResult(
        status=ConfigLoadStatus.OK,
        config_path=repo_result.config_path,
        raw=hierarchical.config.model_dump(mode="json"),
        config=hierarchical.config,
        errors=[],
    )
