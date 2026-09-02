"""Config CLI subpackage."""

from .app import config_app
from .formatters import register_config_formatters

register_config_formatters()

__all__ = ["config_app", "register_config_formatters"]
