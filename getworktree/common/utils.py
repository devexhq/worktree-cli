"""Shared Rich console helpers for consistent CLI output."""

from rich.console import Console
from rich.panel import Panel

console = Console()


def print_spacer() -> None:
    """Print a blank line."""
    console.print()


def print_success(message: str) -> None:
    """Print a green success line."""
    console.print(f"[bold green]✔  {message}[/bold green]")


def print_error_panel(title: str, message: str) -> None:
    """Print a red-bordered panel for errors."""
    console.print(
        Panel.fit(
            f"[bold red]{title}[/bold red]\n{message}",
            border_style="red",
        )
    )


def print_info(message: str) -> None:
    """Print a plain message."""
    console.print(message)


def print_dim_bullet(message: str) -> None:
    """Print a dim bullet list item."""
    console.print(f"  [dim]•[/dim] {message}")


def print_dim(message: str) -> None:
    """Print dim-styled text."""
    console.print(f"[bold dim]{message}[/bold dim]")
