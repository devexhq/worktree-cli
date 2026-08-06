"""CLI command package for listing and showing built-in templates."""

from getworktree.commands.templates.command import (
    template_show_command,
    templates_list_command,
)
from getworktree.commands.templates.models import (
    TemplatesCommandOutcome,
    TemplateShowCommandOutcome,
)

__all__ = [
    "TemplateShowCommandOutcome",
    "TemplatesCommandOutcome",
    "template_show_command",
    "templates_list_command",
]
