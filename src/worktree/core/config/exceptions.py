"""Config domain exceptions."""

from __future__ import annotations


class ConfigLoadError(RuntimeError):
    """Raised by Config accessor properties when config.json cannot be loaded."""
