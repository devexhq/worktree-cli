"""Shared Rich console helpers for consistent CLI output."""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel


class RichOutput:
    """Rich console helpers for consistent CLI output."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

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

    def error(self, message: str) -> None:
        """Print an error message."""
        self.console.print(message)

    def info(self, message: str) -> None:
        """Print a plain message."""
        self.console.print(message)

    def dim_bullet(self, message: str) -> None:
        """Print a dim bullet list item."""
        self.console.print(f"  [dim]•[/dim] {message}")

    def dim_text(self, message: str) -> None:
        """Print dim-styled text."""
        self.console.print(f"[bold dim]{message}[/bold dim]")


def display_path(path: Path, cwd: Path | None = None) -> str:
    """Display a path, preferring POSIX-style relative segments when possible."""
    if cwd:
        try:
            return path.relative_to(cwd).as_posix()
        except ValueError:
            return str(path)

    try:
        return path.as_posix()
    except Exception:
        return str(path)


def resolve_path_from_config(config_file: Path, path_key: str, default: str | Path) -> Path:
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


def enum_value(value: object) -> str:
    """Return `value.value` when present (enum-like), ekse `str(value)`."""
    return value.value if hasattr(value, "value") else str(value)
