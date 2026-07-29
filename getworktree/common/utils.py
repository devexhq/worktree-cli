"""Shared Rich console helpers for consistent CLI output."""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel


class RichOutput:
    """Rich console helpers for consistent CLI output."""

    def __init__(self):
        self.console = Console()

    def spacer(self) -> None:
        """Print a blank line."""
        self.console.print()

    def success(self, message: str) -> None:
        """Print a green success line."""
        self.console.print(f"[bold green]✔  {message}[/bold green]")

    def error_panel(self, title: str, message: str) -> None:
        """Print a red-bordered panel for errors."""
        self.console.print(
            Panel.fit(
                f"[bold red]{title}[/bold red]\n{message}",
                border_style="red",
            )
        )

    def info(self, message: str) -> None:
        """Print a plain message."""
        self.console.print(message)

    def dim_bullet(self, message: str) -> None:
        """Print a dim bullet list item."""
        self.console.print(f"  [dim]•[/dim] {message}")

    def dim_text(self, message: str) -> None:
        """Print dim-styled text."""
        self.console.print(f"[bold dim]{message}[/bold dim]")


def display_relative_path(cwd: Path, path: Path) -> str:
    """Display a path relative to the current working directory.

    If the path is not relative to the current working directory, return the absolute path.
    """
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


def resolve_path_from_config(
    config_file: Path, path_key: str, default: str | Path
) -> Path:
    """Resolve a path from a config file.

    If the config file does not exist, return the default path.
    If the path key is not in the config file, return the default path.
    """
    if not config_file.is_file():
        return Path(default)
    with open(config_file, encoding="utf-8") as f:
        raw = json.load(f)
    paths = raw.get("paths")
    if isinstance(paths, dict) and paths.get(path_key):
        return Path(paths[path_key])
    return Path(default)
