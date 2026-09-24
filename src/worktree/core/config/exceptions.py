"""Config domain exceptions."""

from __future__ import annotations

from pathlib import Path

from worktree.core.config.models import ConfigTier


class ConfigLoadError(RuntimeError):
    """Raised by Config accessor properties when config.json cannot be loaded."""


class ConfigTierValidationError(Exception):
    """Raised when a config tier file is unreadable, malformed, or fails WorktreeConfig validation."""

    def __init__(self, tier: ConfigTier, path: Path, details: str) -> None:
        """Format a tier-attributed validation message and retain its parts for callers."""
        super().__init__(f"Invalid configuration in {tier} layer ({path}): {details}")
        self.tier = tier
        self.path = path
        self.details = details
