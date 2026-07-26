import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from getworktree.commands.init import init_command
from getworktree.commands.loop import loop_command
from getworktree.commands.status import status_command

# Initialize a central styling console for high-utility layout parsing
console = Console()

# Package Metadata matching our PyPI footprint
__version__ = "0.1.1"

# Initialize Typer App with clean configuration defaults
app = typer.Typer(
    name="wt",
    help="Isolated git worktree developer loops and autonomous AI agent workspaces.",
    add_completion=True,
    rich_markup_mode="rich",
)


def print_welcome_banner():
    """Renders a highly scannable, developer-focused ASCII brand panel."""
    banner_text = Text()
    banner_text.append("🌳 Worktree CLI ", style="bold green")
    banner_text.append(f"v{__version__}\n", style="dim cyan")
    banner_text.append(
        "Isolated Git Workspaces & Self-Healing Agent Loops", style="italic zinc-400"
    )

    console.print(
        Panel(banner_text, border_style="green", expand=False, padding=(1, 4))
    )


def version_callback(value: bool):
    """Callback function to handle explicit version printing flags."""
    if value:
        console.print(f"[bold green]Worktree CLI[/bold green] v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable extensive internal engineering telemetry logging.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print the current version of the Worktree CLI and exit.",
    ),
):
    """Global configuration wrapper managing shared application context."""
    # Stash verbose settings inside the runtime context dict for downstream commands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # If the developer types just 'wt' without a subcommand, render banner and help
    if ctx.invoked_subcommand is None:
        print_welcome_banner()
        console.print(ctx.get_help())
        raise typer.Exit()
    elif verbose:
        console.print(
            "[dim yellow][TELEMETRY] Global verbose tracking layer active.[/dim yellow]"
        )


@app.command(name="init")
def init_workspace(ctx: typer.Context):
    """Provision a secure local hidden folder path and tracking schemas."""

    """
    verbose = ctx.obj.get("verbose", False)
    console.print("\n[bold blue]⏳ Provisioning secure environment configurations...[/bold blue]")
    console.print("[dim zinc-400]Target tracking issue: #2[/dim zinc-400]")
    if verbose:
        console.print("[dim yellow][TELEMETRY] Initialization hook loaded successfully.[/dim yellow]")
    # Core system verification and file tree generation logic hooks here in Issue #2
    """
    init_command(tool_version=__version__)


@app.command(name="status")
def workspace_status(ctx: typer.Context):
    """Workspace Status."""
    status_command()


@app.command(name="loop")
def loop(
    command: str = typer.Argument(..., help="Target test or build command string."),
):
    """Run command in isolated sandbox and extract error diagnostic payloads."""
    loop_command(command)


# @app.command(name="loop")
# def execute_loop(
#     ctx: typer.Context,
#     step_command: str = typer.Argument(
#         ...,
#         help="The target terminal execution hook (e.g. 'pytest tests/')"
#     ),
#     max_loops: int = typer.Option(
#         5,
#         "--max-loops", "-m",
#         help="Maximum iterative self-healing agent repair sequences."
#     )
# ):
#     """Execute a self-healing background automation sequence against a target pipeline."""
#     verbose = ctx.obj.get("verbose", False)
#     console.print("\n[bold green]🌳 Initializing isolated background context thread...[/bold green]")
#     console.print(f"[bold white]Target Execution Hook:[/bold white] `{step_command}`")
#     console.print(f"[dim zinc-400]Maximum loop constraints set to: {max_loops}[/dim zinc-400]")
#     if verbose:
#         console.print("[dim yellow][TELEMETRY] Sandbox validation pass complete.[/dim yellow]")
#     # Background worktree spawning and subprocess piping hooks here in Issue #6

if __name__ == "__main__":
    app()
