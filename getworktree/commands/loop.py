"""
getworktree/commands/loop.py

Executes target command strings (e.g. test suites) inside an isolated background sandbox,
captures failure diagnostics into formatted payload blocks, and logs token financial audits.
"""

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from getworktree.core.config_manager import display_context_warnings, load_context
from getworktree.core.db import get_session_total_cost, record_token_usage
from getworktree.core.git_sandbox import sandbox_scope

console = Console()


@dataclass
class ExecutionResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    passed: bool


def run_command_in_sandbox(command: str, sandbox_path: Path) -> ExecutionResult:
    """Execute a target shell command inside the background sandbox directory."""
    try:
        process = subprocess.run(
            command,
            cwd=sandbox_path,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        passed = process.returncode == 0
        return ExecutionResult(
            command=command,
            returncode=process.returncode,
            stdout=process.stdout.strip(),
            stderr=process.stderr.strip(),
            passed=passed,
        )
    except Exception as e:  # noqa: BLE001
        return ExecutionResult(
            command=command,
            returncode=1,
            stdout="",
            stderr=f"System execution exception: {e!s}",
            passed=False,
        )


def format_error_payload(
    result: ExecutionResult, branch_name: str, session_id: str
) -> str:
    """Format structured diagnostic payload block for downstream LLM routers."""
    diagnostics = result.stderr if result.stderr else result.stdout
    if not diagnostics:
        diagnostics = "No output captured on stderr or stdout."

    payload = f"""--- AGENT SELF-HEALING DIAGNOSTIC PAYLOAD ---
Session ID: {session_id}
Git Branch: {branch_name}
Executed Command: `{result.command}`
Process Exit Code: {result.returncode}

--- ERROR DIAGNOSTICS & TRACEBACK ---
{diagnostics}
---------------------------------------------"""
    return payload


def loop_command(
    command: str = typer.Argument(
        ..., help="Target command string to run inside sandbox (e.g. 'pytest tests/')."
    ),
    mock_prompt_tokens: int = 500,
    mock_completion_tokens: int = 200,
    mock_cost: float = 0.002,
    # mock_prompt_tokens: int = typer.Option(
    #     500,
    #     "--prompt-tokens",
    #     help="Prompt tokens used for this loop step (mocked/estimated).",
    # ),
    # mock_completion_tokens: int = typer.Option(
    #     200,
    #     "--completion-tokens",
    #     help="Completion tokens used for this loop step (mocked/estimated).",
    # ),
    # mock_cost: float = typer.Option(
    #     0.002, "--cost", help="Estimated USD cost for model execution."
    # ),
):
    """
    Run automated commands in an isolated background worktree and intercept failures.
    """
    cwd = Path.cwd().resolve()
    session_id = f"loop_{uuid.uuid4().hex[:8]}"

    # 1. Load context & display pre-flight warnings (Issue #3)
    try:
        ctx = load_context(cwd)
    except Exception as e:  # noqa: BLE001
        console.print(f"[bold red]Initialization Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    display_context_warnings(ctx)

    console.print(
        f"\n[bold cyan]🔄 Initializing self-healing loop session:[/bold cyan] [dim]{session_id}[/dim]"
    )
    console.print(f"[bold]Target Command:[/bold] [yellow]{command}[/yellow]\n")

    # 2. Execute within isolated background sandbox (Issue #5)
    with sandbox_scope(cwd=cwd, session_id=session_id) as session:
        console.print("🧪 Executing command in isolated sandbox...")
        result = run_command_in_sandbox(command, session.sandbox_path)

        # 3. Handle Results
        if result.passed:
            console.print(
                Panel.fit(
                    "[bold green]✔ Execution Passed Perfectly![/bold green]\n"
                    f"Command [bold]{command}[/bold] completed with exit code 0.",
                    border_style="green",
                )
            )
        else:
            console.print(
                f"[bold red]❌ Command execution failed (Exit Code {result.returncode}).[/bold red]\n"
            )

            # Format diagnostic payload block
            payload = format_error_payload(result, ctx.current_branch, session_id)

            console.print(
                Panel(
                    Syntax(payload, "text", theme="monokai", word_wrap=True),
                    title="[bold yellow]Self-Healing LLM Diagnostic Payload[/bold yellow]",
                    border_style="yellow",
                )
            )

        # 4. Record token financial usage into SQLite audit database (Issue #4)
        model_id = ctx.config.model_path or "default_llm_router"
        record_token_usage(
            session_id=session_id,
            branch_name=ctx.current_branch,
            model_id=model_id,
            prompt_tokens=mock_prompt_tokens,
            completion_tokens=mock_completion_tokens,
            estimated_usd_cost=mock_cost,
            cwd=cwd,
        )

        session_cost = get_session_total_cost(session_id, cwd=cwd)
        console.print(
            f"\n[dim]💾 Audited Session Spend:[/dim] [green]${session_cost['total_usd_cost']:.4f}[/green] "
            f"([dim]{session_cost['total_tokens']} tokens logged to .worktree/token_audit.db[/dim])"
        )


# Typer command registration hook
app = typer.Typer()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    command: str = typer.Argument("pytest", help="Command to execute in sandbox."),
):
    if ctx.invoked_subcommand is None:
        loop_command(command)
