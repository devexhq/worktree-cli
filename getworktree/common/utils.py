from rich.console import Console
from rich.panel import Panel

console = Console()


def print_spacer() -> None:
    console.print()

def print_success(message: str) -> None:
    console.print(f"[bold green]✔  {message}[/bold green]")


def print_error_panel(title: str, message: str) -> None:
    console.print(
        Panel.fit(
            f"[bold red]{title}[/bold red]\n{message}",
            border_style="red",
        )
    )


def print_info(message: str) -> None:
    console.print(message)


def print_dim_bullet(message: str) -> None:
    console.print(f"  [dim]•[/dim] {message}")


def print_dim(message: str) -> None:
    console.print(f"[bold dim]{message}[/bold dim]")
