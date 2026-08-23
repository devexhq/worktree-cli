"""Shared Rich console helpers for consistent CLI output."""

import json
from collections.abc import Iterable
from pathlib import Path

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table


class RichOutput:
    """Rich console builder accumulating renderables for single-action printing."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._items: list[RenderableType | str] = []

    def spacer(self) -> None:
        """Add a blank line."""
        self._items.append("")

    def success(self, message: str) -> None:
        """Add a green success line."""
        self._items.append(f"[bold green]✔  {message}[/bold green]")

    def error_panel(self, title: str, message: str) -> None:
        """Add a red-bordered panel for errors."""
        self._items.append(
            Panel.fit(
                f"[bold red]{title}[/bold red]\n{message}",
                border_style="red",
            )
        )

    def error(self, message: str) -> None:
        """Add an error message."""
        self._items.append(message)

    def info(self, message: str | RenderableType) -> None:
        """Add a plain message or Rich renderable."""
        self._items.append(message)

    def dim_bullet(self, message: str) -> None:
        """Add a dim bullet list item."""
        self._items.append(f"  [dim]•[/dim] {message}")

    def dim_text(self, message: str) -> None:
        """Add dim-styled text."""
        self._items.append(f"[bold dim]{message}[/bold dim]")

    def add_line(self, message: str | RenderableType) -> None:
        """Add a message or renderable item."""
        self.info(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.error(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.info(f"[yellow]Warning:[/] {message}")

    def add_error_panel(self, title: str, message: str) -> None:
        """Add an error panel."""
        self.error_panel(title, message)

    def add_kv_table(self, rows: Iterable[tuple[str, str]]) -> None:
        """Add a key-value detail table."""
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        table.add_column(style="bold")
        table.add_column()
        for key, value in rows:
            table.add_row(f"{key}:", value)
        self._items.append(table)

    def render_not_initialized(self, errors: list[str], *, fix_hint: str) -> None:
        """Add standardized not-initialized error panel."""
        message = "\n\n".join(errors) if errors else f".worktree/config.json not found.\nFix:\n- {fix_hint}"
        self.error_panel("Worktree Not Initialized", message)

    def print(self) -> None:
        """Flush and print all accumulated renderables to the console."""
        for item in self._items:
            self.console.print(item)
        self._items.clear()


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
        # Intentional fallback for path types that don't support as_posix();
        # display_path has no error-reporting channel.
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
    """Return `value.value` when present (enum-like), else `str(value)`."""
    attr = getattr(value, "value", None)
    return attr if isinstance(attr, str) else str(value)
